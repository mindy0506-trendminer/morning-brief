"""End-to-end dry-run pipeline tests.

These tests exercise the full pipeline using fixture data with zero network calls.
"""

from __future__ import annotations

import email
import email.header
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
    """Execute the dry-run pipeline programmatically and return (eml_path, run_row)."""
    from morning_brief import collector, selector, summarizer
    from morning_brief.db import bootstrap, insert_run, update_run_completed
    from morning_brief.renderer import render_and_write

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

    # Render
    t0 = time.time()
    ki_by_id = {ki.cluster_id: ki for ki in key_issues_all}
    output_dir = tmp_path / "out"
    eml_path, subject = render_and_write(
        briefing=briefing,
        key_issues_by_cluster_id=ki_by_id,
        today=now.date(),
        sender="Brief <brief@example.com>",
        recipients=["team@example.com"],
        output_dir=output_dir,
        redact_recipients=False,
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
    return eml_path, run_data


# ---------------------------------------------------------------------------
# 1. Full dry-run pipeline completes and produces valid EML
# ---------------------------------------------------------------------------

def test_dry_run_pipeline_completes(tmp_path: Path) -> None:
    eml_path, run_data = _run_dry_run_pipeline(tmp_path)

    # EML file exists
    assert eml_path.exists(), f"EML file not found at {eml_path}"
    assert eml_path.suffix == ".eml"

    # Parse as email
    msg = email.message_from_bytes(eml_path.read_bytes())
    assert msg.is_multipart()

    content_types = {part.get_content_type() for part in msg.walk()}
    assert "text/plain" in content_types
    assert "text/html" in content_types

    # Subject must be set and non-empty (decode RFC 2047 encoding)
    raw_subject = msg["Subject"] or ""
    decoded_parts = email.header.decode_header(raw_subject)
    subject = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in decoded_parts
    )
    assert subject.startswith("[소비재 트렌드 조간]")


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
    eml_path, _ = _run_dry_run_pipeline(tmp_path)
    assert eml_path.exists()


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
    single Fashion item whose bundle exposes both publisher URLs, and the
    persisted cluster row flags is_cross_lingual_merge=1.

    This test exercises the same pipeline as test_dry_run_pipeline_completes but
    asserts on content, not just structure — it would have caught the MAJOR_GAP
    where deterministic fixture IDs failed to match UUID-based candidate IDs.
    """
    eml_path, _ = _run_dry_run_pipeline(tmp_path)
    assert eml_path.exists()

    # Parse EML → grab HTML part for URL assertions
    msg = email.message_from_bytes(eml_path.read_bytes())
    html_payload = ""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            raw = part.get_payload(decode=True)
            if raw:
                html_payload = raw.decode("utf-8", errors="replace")
                break
    assert html_payload, "text/html part missing from EML"

    # Both publisher URLs from the cross-lingual pair must appear
    assert "businessoffashion.com" in html_payload, (
        "EN publisher URL missing — cross-lingual merge did not emit both sources"
    )
    assert "fashionbiz.co.kr" in html_payload, (
        "KO publisher URL missing — cross-lingual merge did not emit both sources"
    )

    # Inspect persisted cluster artefacts. The dry-run pipeline persists runs
    # into the real .omc/state/briefing/briefing.db regardless of tmp_path,
    # but the call_b_request.json for this specific run lives under tmp_path
    # is not correct — the summarizer writes to _RUN_STATE_DIR (a module path).
    # We therefore load the Call B request artefact from the module path.
    from morning_brief.summarizer import _RUN_STATE_DIR

    # The helper returned run_data; re-derive the run_id used from tmp_path.
    # We also have access to the DB via a fresh connection to the same module DB.
    # Find a cluster_0001 row with is_cross_lingual_merge=1 in the DB path used
    # by the helper (the helper wrote clusters into tmp_path/briefing.db).
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
