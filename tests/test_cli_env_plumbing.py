"""PR-5 — MB_MAX_COST_USD pre-flight guard + MB_FORCE_PARTIAL_BANNER hook.

These exercise the CLI helpers directly; the production pipeline wiring is
covered by the existing dry-run end-to-end test.
"""

from __future__ import annotations

import os

import pytest

from morning_brief import cli


def test_preflight_no_cap_is_noop(monkeypatch):
    monkeypatch.delenv("MB_MAX_COST_USD", raising=False)
    # Must not raise / exit when the cap is unset.
    cli._preflight_cost_check()


def test_preflight_below_cap_passes(monkeypatch):
    monkeypatch.setenv("MB_MAX_COST_USD", "1.5")
    monkeypatch.setenv("MB_PREFLIGHT_ESTIMATE_USD", "0.10")
    cli._preflight_cost_check()  # should NOT exit


def test_preflight_above_cap_exits_with_5(monkeypatch):
    monkeypatch.setenv("MB_MAX_COST_USD", "0.05")
    monkeypatch.setenv("MB_PREFLIGHT_ESTIMATE_USD", "1.00")
    with pytest.raises(SystemExit) as exc:
        cli._preflight_cost_check()
    assert exc.value.code == cli._EXIT_COST_CAP == 5


def test_preflight_invalid_cap_exits(monkeypatch):
    monkeypatch.setenv("MB_MAX_COST_USD", "not-a-number")
    with pytest.raises(SystemExit) as exc:
        cli._preflight_cost_check()
    # Usage errors use exit 1 (per existing _require_env contract).
    assert exc.value.code == 1


def test_force_partial_banner_env(monkeypatch):
    monkeypatch.setenv("MB_FORCE_PARTIAL_BANNER", "1")
    reason = cli._partial_banner_reason_from_env()
    assert reason is not None
    assert "전일" in reason
    assert "자동 재시도" in reason


def test_force_partial_banner_default_off(monkeypatch):
    monkeypatch.delenv("MB_FORCE_PARTIAL_BANNER", raising=False)
    assert cli._partial_banner_reason_from_env() is None
