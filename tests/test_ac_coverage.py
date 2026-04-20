"""Explicit AC gap coverage tests.

Covers:
  AC5  — source URLs capped at 3, deduplicated, all http(s)
  AC7  — run_duration_seconds < 600 via dry-run
  AC11 — rendered index.html is valid HTML with non-empty content
          (PR-4 superseded the pre-existing "EML parseable" variant — the
          EML renderer is retired; the site generator is now sole output.)
  AC12 — fewer than 3 distinct source_names → SystemExit(2) with clear message
  AC15 — per-stage absolute duration caps satisfied on dry-run
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Shared pipeline helper (mirrors test_end_to_end_dry_run._run_dry_run_pipeline)
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _run_dry_run_pipeline(tmp_path: Path) -> tuple[Path, dict]:
    """Execute dry-run pipeline, return (index_path, run_row dict)."""
    from morning_brief import collector, selector, summarizer
    from morning_brief.db import bootstrap, insert_run, update_run_completed
    from morning_brief.site.site_generator import generate_site

    db_path = tmp_path / "briefing.db"
    conn = bootstrap(db_path)

    now = datetime(2026, 4, 18, 7, 0, 0)
    run_id = f"2026-04-18-070000-ac-{id(tmp_path)}"

    insert_run(conn, run_id, now)

    stage_durations: dict[str, float] = {}
    run_notes: list[str] = []

    t0 = time.time()
    articles, collect_errors = collector.collect(conn, now, dry_run=True)
    stage_durations["collect"] = time.time() - t0
    run_notes.extend(collect_errors)

    t0 = time.time()
    scored_candidates = selector.select(conn, articles, now, dry_run=True)
    stage_durations["select"] = time.time() - t0

    articles_by_id = {a.id: a for a in articles}

    stage_timings: dict[str, float] = {}
    briefing, key_issues_all, summ_notes, llm_usage = summarizer.run_summarizer(
        conn=conn,
        scored_candidates=scored_candidates,
        articles_by_id=articles_by_id,
        today=now,
        run_id=run_id,
        dry_run=True,
        api_key="dry-run-key",
        stage_timings=stage_timings,
    )
    run_notes.extend(summ_notes)

    stage_durations["call_a"] = stage_timings.get("call_a", 0.0)
    stage_durations["call_b"] = stage_timings.get("call_b", 0.0)

    t0 = time.time()
    ki_by_id = {ki.cluster_id: ki for ki in key_issues_all}
    output_dir = tmp_path / "out"
    index_path = generate_site(
        briefing=briefing,
        output_dir=output_dir,
        today=now.date(),
        key_issues_by_cluster_id=ki_by_id,
    )
    stage_durations["render"] = time.time() - t0

    completed_at = datetime(2026, 4, 18, 7, 1, 0)
    update_run_completed(
        conn=conn,
        run_id=run_id,
        completed_at=completed_at,
        stage_durations=stage_durations,
        llm_usage=llm_usage,
        notes=" | ".join(run_notes),
    )

    row = conn.execute(
        "SELECT * FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    run_data = dict(row)
    conn.close()
    return index_path, run_data


# ---------------------------------------------------------------------------
# AC5 — source URLs capped at 3, deduplicated, all http(s)
# ---------------------------------------------------------------------------


def test_ac5_primary_source_link_is_http() -> None:
    """The site renderer emits one primary source URL per card. Verify that
    URL is http(s) and is taken from ``article_bundle[0]`` (canonical URL
    preferred). PR-4 scoped-down from the old "cap at 3 + dedup" contract,
    which was EML-specific; site cards show a single primary source."""
    from datetime import datetime as dt
    from morning_brief.models import Article, BriefingItem, KeyIssue, LLMBriefing
    from morning_brief.site.renderer_adapter import build_template_context

    def _make_article(idx: int, url: str) -> Article:
        return Article(
            id=f"art_{idx}",
            title=f"Article {idx}",
            source_name=f"Source{idx}",
            source_type="TraditionalMedia",
            url=url,
            canonical_url=url,
            language="en",
            published_at=dt(2026, 4, 18, 6, 0, 0),
            category="패션",
            raw_summary="Summary",
            enriched_text=None,
            fetched_at=dt(2026, 4, 18, 6, 0, 0),
            extracted_entities=[],
        )

    primary_url = "https://example.com/shared-article"
    bundle = [
        _make_article(0, primary_url),
        _make_article(1, "https://example.com/article-1"),
        _make_article(2, "https://example.com/article-2"),
    ]

    ki = KeyIssue(
        cluster_id="cluster_test",
        category="패션",
        canonical_entity_ko="테스트",
        primary_entity="Test",
        novelty_score=0.7,
        diffusion_score=0.5,
        combined_score=0.6,
        article_bundle=bundle,
    )

    briefing = LLMBriefing(
        schema_version="v2",
        exec_summary_ko=["Line 1", "Line 2", "Line 3"],
        sections={
            "패션": [
                BriefingItem(
                    cluster_id="cluster_test",
                    title_ko="테스트 기사",
                    summary_ko="요약입니다.",
                    is_paywalled=False,
                )
            ]
        },
        misc_observations_ko=None,
        insight_box_ko="인사이트.",
    )

    context = build_template_context(
        briefing,
        {"cluster_test": ki},
        today_iso="2026-04-18",
    )

    tabs = context["tabs"]
    fashion_tab = next((t for t in tabs if t.key == "패션"), None)
    assert fashion_tab is not None, (
        f"패션 tab missing; got {[t.key for t in tabs]}"
    )
    cards = fashion_tab.cards
    assert len(cards) == 1, f"expected 1 card, got {len(cards)}"
    card = cards[0]

    # Primary source URL is the article bundle's first article.
    assert card.source_url == primary_url, (
        f"expected primary source_url={primary_url!r}, got {card.source_url!r}"
    )
    assert card.source_url.startswith("http"), (
        f"source_url does not start with http: {card.source_url!r}"
    )


# ---------------------------------------------------------------------------
# AC7 — run_duration_seconds < 600 (smoke via dry-run)
# ---------------------------------------------------------------------------


def test_ac7_run_duration_under_10min_dry_run(tmp_path: Path) -> None:
    """Dry-run pipeline's logged run_duration_seconds must be < 600."""
    _, run_data = _run_dry_run_pipeline(tmp_path)

    duration = run_data.get("run_duration_seconds")
    assert duration is not None, "run_duration_seconds not recorded"
    assert duration < 600, (
        f"run_duration_seconds={duration:.2f} exceeds AC7 cap of 600s"
    )


# ---------------------------------------------------------------------------
# AC11 — rendered index.html is a non-empty HTML document
# (PR-4: replaces the original EML-parseability variant)
# ---------------------------------------------------------------------------


def test_ac11_index_html_is_valid_document(tmp_path: Path) -> None:
    """index.html must exist, be non-empty, and look like an HTML document."""
    index_path, _ = _run_dry_run_pipeline(tmp_path)

    assert index_path.exists(), f"index.html missing at {index_path}"
    html = index_path.read_text(encoding="utf-8")
    assert html.strip(), "index.html is empty"
    lowered = html.lower()
    assert "<html" in lowered or "<!doctype" in lowered, (
        "index.html does not look like an HTML document"
    )


# ---------------------------------------------------------------------------
# AC12 — insufficient feeds → SystemExit(2) with clear message
# ---------------------------------------------------------------------------


def test_ac12_insufficient_feeds_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI run aborts with SystemExit(2) when fewer than 3 feeds contribute articles."""
    from datetime import datetime as dt
    from morning_brief.models import Article

    def _make_article(source: str, idx: int) -> Article:
        return Article(
            id=f"art_{source}_{idx}",
            title=f"Article {idx} from {source}",
            source_name=source,
            source_type="TraditionalMedia",
            url=f"https://{source}.example.com/article-{idx}",
            canonical_url=f"https://{source}.example.com/article-{idx}",
            language="en",
            published_at=dt(2026, 4, 18, 6, 0, 0),
            category="식음료",
            raw_summary="Summary.",
            enriched_text=None,
            fetched_at=dt(2026, 4, 18, 6, 0, 0),
            extracted_entities=[],
        )

    # Only 2 distinct source_names
    thin_articles = [
        _make_article("source-a", 1),
        _make_article("source-a", 2),
        _make_article("source-b", 3),
    ]

    import morning_brief.collector as collector_mod

    # Patch collect() to return articles from only 2 sources
    monkeypatch.setattr(
        collector_mod,
        "collect",
        lambda conn, now, dry_run=False: (thin_articles, []),
    )

    import morning_brief.cli as cli_mod
    import morning_brief.db as db_mod
    from morning_brief.db import bootstrap

    db_path = tmp_path / "briefing.db"
    conn = bootstrap(db_path)

    # bootstrap and insert_run are imported locally inside _run_pipeline,
    # so we patch them on the db module itself.
    monkeypatch.setattr(db_mod, "bootstrap", lambda path: conn)
    monkeypatch.setattr(db_mod, "insert_run", lambda *a, **kw: None)

    import argparse
    args = argparse.Namespace(limit_per_cat=None)

    # Patch env vars required by cmd_run
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("BRIEF_SENDER", "Brief <brief@example.com>")
    monkeypatch.setenv("BRIEF_RECIPIENTS", "team@example.com")

    with pytest.raises(SystemExit) as exc_info:
        cli_mod.cmd_run(args)

    assert exc_info.value.code == 2, (
        f"Expected SystemExit(2), got SystemExit({exc_info.value.code})"
    )


def test_ac12_message_mentions_feeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The AC12 abort message mentions 'feeds' and the count."""
    from datetime import datetime as dt
    from morning_brief.models import Article

    def _make_article(source: str, idx: int) -> Article:
        return Article(
            id=f"art2_{source}_{idx}",
            title=f"Article {idx}",
            source_name=source,
            source_type="TraditionalMedia",
            url=f"https://{source}.example.com/{idx}",
            canonical_url=f"https://{source}.example.com/{idx}",
            language="en",
            published_at=dt(2026, 4, 18, 6, 0, 0),
            category="식음료",
            raw_summary="S.",
            enriched_text=None,
            fetched_at=dt(2026, 4, 18, 6, 0, 0),
            extracted_entities=[],
        )

    thin_articles = [_make_article("only-one-source", i) for i in range(3)]

    import morning_brief.collector as collector_mod
    import morning_brief.cli as cli_mod
    import morning_brief.db as db_mod
    from morning_brief.db import bootstrap

    monkeypatch.setattr(
        collector_mod,
        "collect",
        lambda conn, now, dry_run=False: (thin_articles, []),
    )

    db_path = tmp_path / "briefing.db"
    conn = bootstrap(db_path)
    monkeypatch.setattr(db_mod, "bootstrap", lambda path: conn)
    monkeypatch.setattr(db_mod, "insert_run", lambda *a, **kw: None)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("BRIEF_SENDER", "Brief <brief@example.com>")
    monkeypatch.setenv("BRIEF_RECIPIENTS", "team@example.com")

    import argparse
    args = argparse.Namespace(limit_per_cat=None)

    with pytest.raises(SystemExit):
        cli_mod.cmd_run(args)

    captured = capsys.readouterr()
    assert "feeds" in captured.err.lower(), (
        f"Expected 'feeds' in stderr; got: {captured.err!r}"
    )


# ---------------------------------------------------------------------------
# AC15 — per-stage absolute duration caps on dry-run
# ---------------------------------------------------------------------------

_STAGE_CAPS = {
    "collect": 180.0,
    "select": 10.0,
    "call_a": 45.0,
    "call_b": 120.0,
    "render": 5.0,
}


def test_ac15_stage_caps_on_dry_run(tmp_path: Path) -> None:
    """All per-stage durations from a dry-run must be within AC15 hard caps."""
    _, run_data = _run_dry_run_pipeline(tmp_path)

    durations_raw = run_data.get("stage_durations_json") or "{}"
    durations: dict[str, float] = json.loads(durations_raw)

    for stage, cap in _STAGE_CAPS.items():
        assert stage in durations, f"Stage '{stage}' missing from stage_durations_json"
        actual = durations[stage]
        assert actual < cap, (
            f"Stage '{stage}' took {actual:.3f}s, exceeds AC15 cap of {cap}s"
        )
