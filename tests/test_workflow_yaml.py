"""PR-5 — contract tests for ``.github/workflows/daily-brief.yml``.

These tests keep the daily CI/CD pipeline from silently regressing on the
OQ11 retry ladder, the KST timezone, and the concurrency / secret contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WF_PATH = _REPO_ROOT / ".github" / "workflows" / "daily-brief.yml"


def _load() -> dict:
    assert _WF_PATH.exists(), f"missing workflow at {_WF_PATH}"
    return yaml.safe_load(_WF_PATH.read_text(encoding="utf-8"))


def test_workflow_exists():
    assert _WF_PATH.is_file()


def test_workflow_has_cron():
    wf = _load()
    # PyYAML parses the unquoted key `on:` as boolean True; handle both.
    triggers = wf.get("on") or wf.get(True)
    assert triggers, "workflow 'on' block missing"
    schedule = triggers["schedule"]
    crons = [entry["cron"] for entry in schedule]
    assert "0 22 * * *" in crons, f"expected '0 22 * * *' cron, got {crons!r}"


def test_workflow_tz_asia_seoul():
    wf = _load()
    assert wf.get("env", {}).get("TZ") == "Asia/Seoul"


def test_workflow_concurrency_group():
    wf = _load()
    concurrency = wf.get("concurrency")
    assert concurrency, "concurrency block missing"
    assert concurrency.get("group") == "daily-brief"
    assert concurrency.get("cancel-in-progress") is False


def test_workflow_has_retry_steps():
    wf = _load()
    job = next(iter(wf["jobs"].values()))
    step_names = [s.get("name", "") for s in job["steps"]]
    attempts = [n for n in step_names if n.startswith("Attempt")]
    assert len(attempts) == 3, (
        f"expected 3 Attempt steps, found {len(attempts)}: {attempts!r}"
    )


def test_workflow_uses_anthropic_secret():
    wf = _load()
    # Serialize back so we can grep for the exact secret reference regardless
    # of which step carries it.
    text = _WF_PATH.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in text, (
        "ANTHROPIC_API_KEY must be sourced from the repository secret"
    )
    # Cross-check that the job actually references it at least once.
    job = next(iter(wf["jobs"].values()))
    env_blocks = [s.get("env", {}) for s in job["steps"]]
    assert any("ANTHROPIC_API_KEY" in env for env in env_blocks)


def test_workflow_final_attempt_forces_banner():
    """Attempt 3 must set ``MB_FORCE_PARTIAL_BANNER=1`` (OQ11 banner fallback)."""
    wf = _load()
    job = next(iter(wf["jobs"].values()))
    third = next(s for s in job["steps"] if s.get("name", "").startswith("Attempt 3"))
    assert third.get("env", {}).get("MB_FORCE_PARTIAL_BANNER") in ("1", 1)


def test_workflow_pagefind_and_pages_deploy():
    """Pagefind build + actions/deploy-pages must both be present (§D5 / §E)."""
    text = _WF_PATH.read_text(encoding="utf-8")
    assert "npx pagefind" in text, "Pagefind build step missing"
    assert "actions/deploy-pages@" in text, "deploy-pages step missing"
    assert "actions/upload-pages-artifact@" in text, "upload-pages-artifact missing"
