"""PR-4 guards — the EML renderer module and the ``--renderer`` CLI flag
are both retired. These assertions break loudly if anyone reintroduces them
without updating this test.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_renderer_module_is_removed() -> None:
    """``import morning_brief.renderer`` must raise ModuleNotFoundError."""
    with pytest.raises(ModuleNotFoundError):
        import morning_brief.renderer  # noqa: F401


def test_renderer_flag_rejected() -> None:
    """The CLI must not accept ``--renderer=eml`` any more (argparse rejects
    unknown arguments with exit code 2 and an error on stderr)."""
    root = Path(__file__).parent.parent
    script = root / "morning_brief.py"

    env = os.environ.copy()
    env.setdefault("BRIEF_RECIPIENTS", "qa@example.com")
    env.setdefault("BRIEF_SENDER", "Brief <brief@example.com>")

    result = subprocess.run(
        [sys.executable, str(script), "dry-run", "--renderer=eml"],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
        timeout=60,
    )
    assert result.returncode != 0, (
        "Expected non-zero exit when --renderer=eml is supplied; "
        f"got 0. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # argparse writes "unrecognized arguments" on stderr for unknown flags.
    assert "unrecognized" in result.stderr.lower() or "renderer" in result.stderr.lower(), (
        f"Expected argparse rejection message; got stderr={result.stderr!r}"
    )
