"""F6 — mobile breakpoints exist in CSS.

Smoke check: verify the responsive.css file declares at least the
mobile (≤768px) and tablet (≥768px) breakpoints the plan requires.
Keeping this as a file-based grep means the CI doesn't need a headless
browser just to prove the rules ship.
"""

from __future__ import annotations

from pathlib import Path

_CSS_ROOT = Path(__file__).parent.parent / "morning_brief" / "site" / "static" / "css"


def test_responsive_css_has_mobile_breakpoint():
    text = (_CSS_ROOT / "responsive.css").read_text(encoding="utf-8")
    assert "@media (max-width: 768px)" in text


def test_responsive_css_has_tablet_breakpoint():
    text = (_CSS_ROOT / "responsive.css").read_text(encoding="utf-8")
    assert "@media (min-width: 768px)" in text


def test_responsive_css_has_desktop_breakpoint():
    text = (_CSS_ROOT / "responsive.css").read_text(encoding="utf-8")
    assert "@media (min-width: 1200px)" in text


def test_card_summary_uses_line_clamp():
    text = (_CSS_ROOT / "card.css").read_text(encoding="utf-8")
    assert "-webkit-line-clamp: 3" in text


def test_base_uses_clamp_for_fluid_type():
    text = (_CSS_ROOT / "base.css").read_text(encoding="utf-8")
    assert "clamp(" in text


def test_print_css_linearizes_tab_panels():
    text = (_CSS_ROOT / "print.css").read_text(encoding="utf-8")
    # print.css must un-hide hidden tab panels for the PDF output.
    assert "[hidden]" in text
    assert "display: block" in text


def test_print_css_hides_sidebar_and_search():
    text = (_CSS_ROOT / "print.css").read_text(encoding="utf-8")
    assert ".mb-sidebar" in text
    assert ".mb-search" in text


# ---------------------------------------------------------------------------
# PR-2 QA Issue F — mobile drawer CSS contract.
# ---------------------------------------------------------------------------


def test_mobile_sidebar_has_transform_drawer():
    text = (_CSS_ROOT / "responsive.css").read_text(encoding="utf-8")
    assert "translateX(-100%)" in text
    assert ".mb-sidebar.is-open" in text


def test_desktop_hides_backdrop_and_close_button():
    text = (_CSS_ROOT / "responsive.css").read_text(encoding="utf-8")
    # Inside the ≥768px block, both mobile-only chrome elements collapse.
    assert ".mb-backdrop" in text
    assert ".mb-sidebar-close" in text


def test_sidebar_css_declares_backdrop_and_close():
    text = (_CSS_ROOT / "sidebar.css").read_text(encoding="utf-8")
    assert ".mb-backdrop" in text
    assert ".mb-sidebar-close" in text
