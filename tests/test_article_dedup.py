"""Tests for cross-run article-level deduplication.

User requirement (verbatim, Korean):
    "한번 다루었던 기사를 다시 게시하는 일은 없어야 할 것 같아요"
    — An article already briefed must not be published again.

Covers:
  1. briefed_articles table creation on fresh bootstrap
  2. Migration is idempotent (bootstrap twice raises no error)
  3. mark_articles_briefed inserts and is INSERT OR IGNORE idempotent
  4. get_briefed_article_ids returns the expected set
  5. Pipeline filters previously-briefed articles on a second run
  6. Pipeline does NOT mark articles when Call B aborts (SystemExit 4)
  7. MB_NO_DEDUP_PERSIST=1 skips the mark step
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from morning_brief import cli as cli_mod
from morning_brief.db import (
    bootstrap,
    get_briefed_article_canonical_urls,
    get_briefed_article_ids,
    mark_articles_briefed,
    upsert_article,
)
from morning_brief.models import Article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {row["name"] for row in rows}


def _make_article(
    *,
    article_id: str,
    canonical_url: str,
    title: str = "Test",
    lang: str = "ko",
) -> Article:
    now = datetime(2026, 4, 18, 7, 0, 0)
    return Article(
        id=article_id,
        title=title,
        source_name="TestSource",
        source_type="TraditionalMedia",
        url=canonical_url,
        canonical_url=canonical_url,
        language=lang,  # type: ignore[arg-type]
        published_at=now,
        category="패션",
        raw_summary="summary",
        enriched_text=None,
        fetched_at=now,
        extracted_entities=[],
    )


def _run_dry_run_via_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    db_path: Path | None = None,
) -> Path:
    """Run ``cli._run_pipeline`` in dry-run mode with redirected paths.

    Returns the DB path so follow-up runs can reuse it. If ``db_path`` is
    provided, bootstrap is skipped (an existing DB is reused across runs).
    """
    if db_path is None:
        db_path = tmp_path / "briefing.db"
    out_dir = tmp_path / "out"
    monkeypatch.setattr(cli_mod, "_DB_PATH", db_path)
    monkeypatch.setattr(cli_mod, "_DEFAULT_OUTPUT_DIR", out_dir)
    cli_mod._run_pipeline(
        dry_run=True,
        api_key="dry-run-key",
        sender="Brief <b@example.com>",
        recipients=["team@example.com"],
        redact_recipients=False,
        call_a_model="claude-haiku-4-5",
        call_b_model="claude-sonnet-4-6",
        limit_per_cat=None,
    )
    return db_path


# ---------------------------------------------------------------------------
# 1. Table is created on fresh bootstrap
# ---------------------------------------------------------------------------


def test_briefed_articles_table_created(tmp_path: Path) -> None:
    conn = bootstrap(tmp_path / "briefing.db")
    try:
        assert "briefed_articles" in _table_names(conn)
        # Verify expected columns
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(briefed_articles)")
        }
        assert cols == {"article_id", "run_id", "briefed_at", "cluster_id"}
        # Verify index exists
        idx_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='briefed_articles'"
        ).fetchall()
        idx_names = {r["name"] for r in idx_rows}
        assert "idx_briefed_articles_article_id" in idx_names
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. Migration is idempotent
# ---------------------------------------------------------------------------


def test_briefed_articles_migration_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "briefing.db"
    conn1 = bootstrap(db_path)
    conn1.close()
    # Second bootstrap on the same file must not raise
    conn2 = bootstrap(db_path)
    try:
        assert "briefed_articles" in _table_names(conn2)
    finally:
        conn2.close()


def test_briefed_articles_migration_on_legacy_db(tmp_path: Path) -> None:
    """Simulate a pre-existing DB missing ``briefed_articles``; bootstrap
    must add the table without touching the rest of the schema."""
    db_path = tmp_path / "legacy.db"
    # Build a minimal "legacy" DB with the old 5-table set but NO
    # briefed_articles table.
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE articles (
            id TEXT PRIMARY KEY,
            canonical_url TEXT UNIQUE NOT NULL,
            title TEXT,
            source_name TEXT,
            source_type TEXT,
            lang TEXT,
            category TEXT,
            published_at TEXT,
            raw_summary TEXT,
            enriched_text TEXT,
            fetched_at TEXT,
            company_tags TEXT NOT NULL DEFAULT '[]'
        );
        """
    )
    conn.commit()
    conn.close()

    # Now bootstrap on the same path — migration should add briefed_articles.
    conn2 = bootstrap(db_path)
    try:
        assert "briefed_articles" in _table_names(conn2)
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# 3. mark_articles_briefed + INSERT OR IGNORE behaviour
# ---------------------------------------------------------------------------


def test_mark_articles_briefed_inserts(tmp_path: Path) -> None:
    conn = bootstrap(tmp_path / "briefing.db")
    try:
        # Seed articles first — briefed_articles.article_id is FK-constrained.
        for aid in ("a1", "a2", "a3"):
            upsert_article(
                conn,
                _make_article(article_id=aid, canonical_url=f"https://e.com/{aid}"),
            )

        pairs: list[tuple[str, str | None]] = [
            ("a1", "cluster_1"),
            ("a2", "cluster_1"),
            ("a3", None),
        ]
        inserted = mark_articles_briefed(
            conn, pairs, run_id="run-1", briefed_at="2026-04-18T07:00:00Z"
        )
        assert inserted == 3

        rows = conn.execute(
            "SELECT article_id, run_id, cluster_id FROM briefed_articles"
        ).fetchall()
        assert {(r["article_id"], r["run_id"], r["cluster_id"]) for r in rows} == {
            ("a1", "run-1", "cluster_1"),
            ("a2", "run-1", "cluster_1"),
            ("a3", "run-1", None),
        }

        # Re-inserting the same (article_id, run_id) pairs is a no-op
        # thanks to INSERT OR IGNORE on the composite primary key.
        reinserted = mark_articles_briefed(
            conn, pairs, run_id="run-1", briefed_at="2026-04-18T07:00:00Z"
        )
        assert reinserted == 0
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM briefed_articles"
        ).fetchone()["n"]
        assert count == 3

        # Same article_id but a different run_id DOES insert (the PK is
        # composite). This mirrors real multi-run behaviour where the
        # ledger would otherwise only grow — but in practice the filter
        # ensures an id is only ever briefed once.
        reinserted_other_run = mark_articles_briefed(
            conn, [("a1", "cluster_9")], run_id="run-2", briefed_at="x"
        )
        assert reinserted_other_run == 1
    finally:
        conn.close()


def test_mark_articles_briefed_empty_list_is_noop(tmp_path: Path) -> None:
    conn = bootstrap(tmp_path / "briefing.db")
    try:
        inserted = mark_articles_briefed(
            conn, [], run_id="run-1", briefed_at="2026-04-18T07:00:00Z"
        )
        assert inserted == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 4. get_briefed_article_ids returns a set
# ---------------------------------------------------------------------------


def test_get_briefed_article_ids_returns_set(tmp_path: Path) -> None:
    conn = bootstrap(tmp_path / "briefing.db")
    try:
        assert get_briefed_article_ids(conn) == set()

        for aid in ("a1", "a2", "a3"):
            upsert_article(
                conn,
                _make_article(article_id=aid, canonical_url=f"https://e.com/{aid}"),
            )

        mark_articles_briefed(
            conn,
            [("a1", "c1"), ("a2", "c1"), ("a3", None)],
            run_id="run-1",
            briefed_at="2026-04-18T07:00:00Z",
        )
        assert get_briefed_article_ids(conn) == {"a1", "a2", "a3"}

        # Distinct across runs (same article_id surfaces once).
        mark_articles_briefed(
            conn,
            [("a1", "c9")],
            run_id="run-2",
            briefed_at="2026-04-19T07:00:00Z",
        )
        assert get_briefed_article_ids(conn) == {"a1", "a2", "a3"}
    finally:
        conn.close()


def test_get_briefed_article_canonical_urls(tmp_path: Path) -> None:
    conn = bootstrap(tmp_path / "briefing.db")
    try:
        # Seed articles table first (required for the JOIN).
        art1 = _make_article(article_id="a1", canonical_url="https://ex.com/one")
        art2 = _make_article(article_id="a2", canonical_url="https://ex.com/two")
        art3 = _make_article(article_id="a3", canonical_url="https://ex.com/three")
        for a in (art1, art2, art3):
            upsert_article(conn, a)

        mark_articles_briefed(
            conn,
            [("a1", "c1"), ("a2", "c1")],
            run_id="run-1",
            briefed_at="2026-04-18T07:00:00Z",
        )
        urls = get_briefed_article_canonical_urls(conn)
        assert urls == {"https://ex.com/one", "https://ex.com/two"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 5. End-to-end: pipeline filters already-briefed articles on a second run
# ---------------------------------------------------------------------------


def test_pipeline_marks_articles_on_successful_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a successful dry-run, briefed_articles is populated with the
    ids of every article that ended up in a KeyIssue bundle."""
    db_path = _run_dry_run_via_cli(tmp_path, monkeypatch)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT article_id, run_id, briefed_at, cluster_id "
            "FROM briefed_articles"
        ).fetchall()
    finally:
        conn.close()

    assert rows, "Run 1 must populate briefed_articles"
    # Every row has a non-empty run_id and briefed_at
    for r in rows:
        assert r["run_id"]
        assert r["briefed_at"]


def test_pipeline_filters_already_briefed_articles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Inject a synthetic collector that returns the real fixture articles
    PLUS a few extra articles that are already marked as briefed. The
    filter should drop the extras, leaving only the fixture articles for
    the rest of the pipeline (so the dry-run fixtures still line up with
    the mock Call A / Call B responses).

    Asserts:
      - The "Filtered N already-briefed articles" log fires with N == 2.
      - After the pipeline completes, the 2 extra articles still have
        exactly one row each in briefed_articles (under their original
        pre-seed run_id, not a new one).
    """
    import logging

    from morning_brief import collector

    real_collect = collector.collect

    # Build 2 synthetic "already briefed" articles that will be appended
    # to the collector output.
    ghost_articles = [
        _make_article(
            article_id=f"ghost_article_{i}",
            canonical_url=f"https://ghost.example.com/article/{i}",
            title=f"Ghost Article {i}",
            lang="ko",
        )
        for i in range(2)
    ]
    ghost_ids = {a.id for a in ghost_articles}

    def _fake_collect(conn, now, dry_run=False):
        articles, errors = real_collect(conn, now, dry_run=dry_run)
        # Persist ghost articles so the filter can join against the DB
        # if needed, matching real collector behaviour.
        for a in ghost_articles:
            upsert_article(conn, a)
        return articles + list(ghost_articles), errors

    monkeypatch.setattr(collector, "collect", _fake_collect)

    db_path = tmp_path / "briefing.db"
    conn = bootstrap(db_path)
    try:
        # Upsert ghost articles FIRST so the briefed_articles FK constraint
        # is satisfied when we pre-seed.
        for a in ghost_articles:
            upsert_article(conn, a)
        mark_articles_briefed(
            conn,
            [(aid, None) for aid in sorted(ghost_ids)],
            run_id="pre-seed-run",
            briefed_at="2026-04-17T07:00:00Z",
        )
    finally:
        conn.close()

    caplog.set_level(logging.INFO, logger="morning_brief.cli")
    _run_dry_run_via_cli(tmp_path, monkeypatch, db_path=db_path)

    # Filter must have logged its work — exactly 2 filtered (the ghosts).
    filter_logs = [
        rec.getMessage()
        for rec in caplog.records
        if "already-briefed" in rec.getMessage()
    ]
    assert filter_logs, (
        "Expected 'Filtered N already-briefed articles' log message; "
        f"got records: {[r.getMessage() for r in caplog.records]}"
    )
    assert any("Filtered 2" in msg for msg in filter_logs), (
        f"Expected filter to remove exactly 2 ghost articles; got: {filter_logs}"
    )

    # Ghost articles must not appear under any run_id other than the
    # pre-seed one (filter blocked them from reaching the mark step).
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ghost_rows = conn.execute(
            "SELECT article_id, run_id FROM briefed_articles "
            "WHERE article_id IN (?, ?)",
            tuple(sorted(ghost_ids)),
        ).fetchall()
    finally:
        conn.close()

    assert len(ghost_rows) == 2
    for r in ghost_rows:
        assert r["run_id"] == "pre-seed-run", (
            f"ghost article {r['article_id']} got re-briefed under "
            f"run_id={r['run_id']!r}; filter is not working"
        )


# ---------------------------------------------------------------------------
# 6. No marking on Call B abort
# ---------------------------------------------------------------------------


def test_pipeline_no_marking_on_call_b_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the summarizer aborts (SystemExit 4 — Call B failure),
    briefed_articles must remain empty."""
    from morning_brief import summarizer as summ_mod

    def _raise_call_b(*args, **kwargs):
        raise SystemExit(4)

    monkeypatch.setattr(summ_mod, "run_summarizer", _raise_call_b)

    db_path = tmp_path / "briefing.db"
    out_dir = tmp_path / "out"
    monkeypatch.setattr(cli_mod, "_DB_PATH", db_path)
    monkeypatch.setattr(cli_mod, "_DEFAULT_OUTPUT_DIR", out_dir)

    with pytest.raises(SystemExit) as exc:
        cli_mod._run_pipeline(
            dry_run=True,
            api_key="dry-run-key",
            sender="Brief <b@example.com>",
            recipients=["team@example.com"],
            redact_recipients=False,
            call_a_model="claude-haiku-4-5",
            call_b_model="claude-sonnet-4-6",
            limit_per_cat=None,
        )
    assert exc.value.code == 4

    # DB should still exist (bootstrap ran before the abort) and
    # briefed_articles must be empty.
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM briefed_articles"
        ).fetchone()["n"]
    finally:
        conn.close()
    assert count == 0


# ---------------------------------------------------------------------------
# 7. MB_NO_DEDUP_PERSIST env skips the mark step
# ---------------------------------------------------------------------------


def test_mb_no_dedup_persist_env_skips_marking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MB_NO_DEDUP_PERSIST", "1")
    db_path = _run_dry_run_via_cli(tmp_path, monkeypatch)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM briefed_articles"
        ).fetchone()["n"]
    finally:
        conn.close()
    assert count == 0, (
        "MB_NO_DEDUP_PERSIST=1 should suppress marking, but "
        f"briefed_articles has {count} rows"
    )
