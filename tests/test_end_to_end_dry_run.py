"""End-to-end dry-run pipeline tests.

These tests exercise the full pipeline using fixture data with zero network
calls. PR-4: the EML renderer was retired; the site generator is now the
sole renderer and emits ``out/index.html``.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SAMPLE_ARTICLES = _FIXTURES_DIR / "sample_articles.json"
_MOCK_CALL_A = _FIXTURES_DIR / "mock_call_a_response.json"
_MOCK_CALL_B = _FIXTURES_DIR / "mock_call_b_response.json"


def _run_dry_run_pipeline(tmp_path: Path) -> tuple[Path, dict]:
    """Execute the dry-run pipeline programmatically and return (index_path, run_row)."""
    from morning_brief import collector, selector, summarizer
    from morning_brief.db import bootstrap, insert_run, update_run_completed
    from morning_brief.site.site_generator import generate_site

    db_path = tmp_path / "briefing.db"
    conn = bootstrap(db_path)

    now = datetime(2026, 4, 18, 7, 0, 0)
    run_id = f"2026-04-18-070000-{id(tmp_path)}"

    insert_run(conn, run_id, now)

    stage_durations: dict[str, float] = {}
    run_notes: list[str] = []

    # Collect (dry_run loads sample_articles.json)
    t0 = time.time()
    articles, collect_errors = collector.collect(conn, now, dry_run=True)
    stage_durations["collect"] = time.time() - t0
    run_notes.extend(collect_errors)

    # Select (dry_run=True → deterministic candidate IDs cand_001, cand_002, …)
    t0 = time.time()
    scored_candidates = selector.select(conn, articles, now, dry_run=True)
    stage_durations["select"] = time.time() - t0

    articles_by_id = {a.id: a for a in articles}

    # Summarize (dry_run=True uses mock fixtures)
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

    # Render (static site)
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

    # Complete run
    completed_at = datetime(2026, 4, 18, 7, 0, 30)
    update_run_completed(
        conn=conn,
        run_id=run_id,
        completed_at=completed_at,
        stage_durations=stage_durations,
        llm_usage=llm_usage,
        notes=" | ".join(run_notes),
    )

    # Read back the run row
    row = conn.execute(
        "SELECT * FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    run_data = dict(row)

    conn.close()
    return index_path, run_data


# ---------------------------------------------------------------------------
# 1. Full dry-run pipeline completes and produces a valid HTML site
# ---------------------------------------------------------------------------

def test_dry_run_pipeline_completes(tmp_path: Path) -> None:
    index_path, run_data = _run_dry_run_pipeline(tmp_path)

    # The site generator writes index.html at the output root.
    assert index_path.exists(), f"index.html not found at {index_path}"
    assert index_path.suffix == ".html"
    assert index_path.name == "index.html"

    html = index_path.read_text(encoding="utf-8")
    assert html, "index.html is empty"
    # Basic HTML shape — site generator renders a full document.
    assert "<html" in html.lower() or "<!doctype" in html.lower()


# ---------------------------------------------------------------------------
# 2. Zero network calls in dry-run mode
# ---------------------------------------------------------------------------

def test_dry_run_zero_network_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch httpx and anthropic to raise if used — pipeline must still pass."""

    class _BlockedHTTP:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("httpx should not be called in dry-run mode")

        def get(self, *args, **kwargs):
            raise RuntimeError("httpx.get called in dry-run mode")

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    class _BlockedAnthropic:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("anthropic.Anthropic should not be called in dry-run mode")

    import httpx
    import anthropic

    monkeypatch.setattr(httpx, "Client", _BlockedHTTP)
    monkeypatch.setattr(anthropic, "Anthropic", _BlockedAnthropic)

    # Should succeed without raising
    index_path, _ = _run_dry_run_pipeline(tmp_path)
    assert index_path.exists()


# ---------------------------------------------------------------------------
# 3. Stage durations populated
# ---------------------------------------------------------------------------

def test_dry_run_stage_durations_populated(tmp_path: Path) -> None:
    _, run_data = _run_dry_run_pipeline(tmp_path)

    durations_raw = run_data.get("stage_durations_json") or "{}"
    durations = json.loads(durations_raw)

    required_stages = {"collect", "select", "call_a", "call_b", "render"}
    for stage in required_stages:
        assert stage in durations, f"Missing stage: {stage}"
        assert durations[stage] >= 0.0, f"Stage {stage} has negative duration"


# ---------------------------------------------------------------------------
# 4. CLI dry-run completes under 30s (AC1)
# ---------------------------------------------------------------------------

def test_ac8_cross_lingual_merge(tmp_path: Path) -> None:
    """AC8 — the cross_lingual_pair fixture's EN+KO Zara articles collapse into a
    single Fashion item and the persisted cluster row flags
    is_cross_lingual_merge=1.

    PR-4 note: the site renderer exposes only the primary article's URL per
    card (the EN source wins when it is the bundle's first article), so the
    original EML-era "both publisher URLs appear in the body" assertion no
    longer applies. The merge itself is still verified via the DB row and
    via the archive JSON ``languages`` list, which records every language
    seen in the bundle.
    """
    index_path, _ = _run_dry_run_pipeline(tmp_path)
    assert index_path.exists()

    html_payload = index_path.read_text(encoding="utf-8")
    assert html_payload, "index.html is empty"

    # The primary publisher URL appears on the rendered page. For the
    # cross-lingual pair fixture, the merged cluster's primary article is
    # the KO source (fashionbiz.co.kr).
    assert "fashionbiz.co.kr" in html_payload, (
        "Primary (KO) publisher URL missing from rendered site"
    )

    # The EN side of the merge is not rendered as a clickable link (site
    # card shows one primary source) but the archive JSON records every
    # language in the cluster's bundle. Walk archive/YYYY/MM/DD.json
    # looking for a cards_meta entry whose "languages" list contains both
    # "en" and "ko".
    archive_root = (tmp_path / "out").resolve()
    archive_jsons = list(archive_root.rglob("*.json"))
    assert archive_jsons, f"no archive JSON under {archive_root}"
    merged_languages: set[str] = set()
    for jf in archive_jsons:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cards_meta = data.get("cards_meta") or {}
        for meta in cards_meta.values():
            langs = meta.get("languages") or []
            if len(langs) > 1:
                merged_languages.update(langs)
    assert {"en", "ko"}.issubset(merged_languages), (
        "archive JSON did not record an EN+KO cross-lingual merge; "
        f"seen merged languages={merged_languages}"
    )

    # Inspect persisted cluster artefacts. Find a cluster row with
    # is_cross_lingual_merge=1 in the DB path used by the helper.
    db_path = tmp_path / "briefing.db"
    assert db_path.exists(), f"Test DB missing at {db_path}"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT id, category, is_cross_lingual_merge, canonical_entity_ko
            FROM clusters
            WHERE is_cross_lingual_merge = 1
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "No cross-lingual cluster row persisted"
    _cluster_id, category, is_xl, canonical = row
    assert category == "패션"
    assert is_xl == 1
    # Korean canonical entity should be present (Hangul chars)
    assert any("\uac00" <= ch <= "\ud7a3" for ch in canonical), (
        f"canonical_entity_ko does not look Korean: {canonical!r}"
    )


def test_cli_dry_run_completes_under_30s() -> None:
    """Spawn python morning_brief.py dry-run via subprocess; must exit 0 in <30s."""
    root = Path(__file__).parent.parent
    script = root / "morning_brief.py"

    start = time.time()
    result = subprocess.run(
        [sys.executable, str(script), "dry-run"],
        capture_output=True,
        text=True,
        cwd=str(root),
        timeout=60,  # subprocess timeout (not the assertion)
    )
    elapsed = time.time() - start

    assert result.returncode == 0, (
        f"dry-run exited {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert elapsed < 30.0, f"dry-run took {elapsed:.1f}s, expected <30s"
