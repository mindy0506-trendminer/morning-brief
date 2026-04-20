"""PR-3 Task 2 — CLI default renderer is ``site`` (formerly ``eml``).

Running ``python morning_brief.py dry-run`` with no ``--renderer`` flag must
now land at ``out/index.html``. The ``--renderer=eml`` path remains a
supported fallback until PR-4 retires ``morning_brief/renderer.py`` proper.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(cwd: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Execute ``python morning_brief.py dry-run [extra]`` from ``cwd``."""
    env = os.environ.copy()
    # Reset recipients so the run command's _require_env short-circuit never
    # picks up a stale shell export during this subprocess invocation.
    env.setdefault("BRIEF_RECIPIENTS", "qa@example.com")
    env.setdefault("BRIEF_SENDER", "Brief <brief@example.com>")
    script = cwd / "morning_brief.py"
    return subprocess.run(
        [sys.executable, str(script), "dry-run", *extra],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=60,
    )


def test_default_renderer_is_site() -> None:
    """No ``--renderer`` flag → the site generator writes ``out/index.html``."""
    root = Path(__file__).parent.parent
    result = _run(root)
    assert result.returncode == 0, (
        f"dry-run exit={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    # The script prints the rendered output path on stdout. Accept either
    # a POSIX or Windows path separator; only the basename matters.
    stdout = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert stdout.endswith("index.html"), (
        f"expected final stdout line to end with 'index.html', got {stdout!r}"
    )
    # The actual file exists (sanity check).
    assert (root / "out" / "index.html").exists(), (
        "default renderer did not produce out/index.html"
    )


def test_eml_fallback_still_works() -> None:
    """``--renderer=eml`` still writes a ``.eml`` file (legacy path preserved)."""
    root = Path(__file__).parent.parent
    result = _run(root, "--renderer=eml")
    assert result.returncode == 0, (
        f"dry-run --renderer=eml exit={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    stdout = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert stdout.endswith(".eml"), (
        f"expected final stdout line to end with '.eml', got {stdout!r}"
    )
