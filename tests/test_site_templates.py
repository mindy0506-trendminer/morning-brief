"""F3 — SCTEEP badges render only for MacroTab cards; never on industry tabs.

Also exercises the PR-2 QA Issue-A/E/F site invariants:
  * card source links point at per-article URLs, never a bare homepage
  * ``오늘의 요약`` (exec_summary) is no longer rendered on the site
  * ``오늘의 인사이트`` renders above the tab navigation
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from morning_brief.site.site_generator import generate_site
from tests._site_fixtures import make_full_briefing, make_sceep_map


def _panel(html: str, slug: str) -> str:
    m = re.search(
        rf'<section class="mb-tab-panel"\s+id="panel-{slug}"[\s\S]*?</section>',
        html,
    )
    assert m
    return m.group(0)


def test_sceep_chips_present_on_macro_tab(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=15)
    sceep = make_sceep_map(briefing)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
        sceep_by_cluster=sceep,
    )
    html = idx.read_text(encoding="utf-8")
    macro = _panel(html, "macro")
    # At least one sceep chip in the macro panel.
    assert "mb-sceep-row" in macro
    # And a known dimension class from our fixture.
    assert "mb-sceep-economy" in macro


def test_sceep_chips_absent_from_industry_tabs(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=15)
    sceep = make_sceep_map(briefing)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
        sceep_by_cluster=sceep,
    )
    html = idx.read_text(encoding="utf-8")
    for slug in ("fnb", "beauty", "fashion", "lifestyle", "consumer"):
        panel = _panel(html, slug)
        assert "mb-sceep-row" not in panel, (
            f"SCTEEP row leaked into industry tab '{slug}'"
        )


def test_sceep_empty_macro_renders_no_chips(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=15)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
        sceep_by_cluster={},  # no tagging
    )
    html = idx.read_text(encoding="utf-8")
    macro = _panel(html, "macro")
    assert "mb-sceep-row" not in macro


# ---------------------------------------------------------------------------
# PR-2 QA Issue A — card source link points at the article URL, never the
# publisher's homepage.
# ---------------------------------------------------------------------------

_SOURCE_ANCHOR_RE = re.compile(
    r'<footer class="mb-card-source">\s*<a href="([^"]+)"',
)


def test_card_source_link_points_to_article_not_homepage(tmp_path: Path):
    """Every card's source <a href> must resolve to an article-level URL.

    Regression guard for the browser-QA finding where clicking the source
    name navigated to the publisher's homepage instead of the original
    article. The assertion checks that the URL has a non-trivial path
    segment (e.g. ``/article/foo``) so ``example.com`` / ``example.com/``
    style fixtures never sneak back in.
    """
    briefing, ki_map = make_full_briefing(cards_per_tab=5)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    hrefs = _SOURCE_ANCHOR_RE.findall(html)
    assert hrefs, "no card source anchors rendered"
    for href in hrefs:
        parsed = urlparse(href)
        assert parsed.scheme in ("http", "https"), f"non-http(s) href: {href!r}"
        assert parsed.netloc, f"href missing hostname: {href!r}"
        # A bare homepage would have path in ("", "/") — reject that shape.
        assert parsed.path not in ("", "/"), (
            f"source href looks like a homepage, not an article URL: {href!r}"
        )


# ---------------------------------------------------------------------------
# PR-2 QA Issue E — site layout: header → insight → tabs → cards.
# ---------------------------------------------------------------------------


def test_exec_summary_block_not_rendered(tmp_path: Path):
    """``오늘의 요약`` must NOT appear on the site renderer output."""
    briefing, ki_map = make_full_briefing(cards_per_tab=2)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    assert "mb-exec-summary" not in html
    assert "오늘의 요약" not in html


def test_insight_block_renders_before_tabs(tmp_path: Path):
    """``오늘의 인사이트`` block must appear before <nav class="mb-tabs">."""
    briefing, ki_map = make_full_briefing(cards_per_tab=2)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    insight_pos = html.find('class="mb-insight"')
    tabs_pos = html.find('<nav class="mb-tabs"')
    assert insight_pos != -1, "insight block missing"
    assert tabs_pos != -1, "tabs nav missing"
    assert insight_pos < tabs_pos, (
        "insight block must render before the tab navigation "
        f"(insight at {insight_pos}, tabs at {tabs_pos})"
    )


def test_dom_order_header_insight_tabs_cards(tmp_path: Path):
    """Header → insight → tabs → first card panel, in that DOM order."""
    briefing, ki_map = make_full_briefing(cards_per_tab=2)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    header = html.find('class="mb-header"')
    insight = html.find('class="mb-insight"')
    tabs = html.find('<nav class="mb-tabs"')
    panel = html.find('class="mb-tab-panel"')
    assert -1 < header < insight < tabs < panel, (
        f"unexpected DOM order: header={header} insight={insight} "
        f"tabs={tabs} panel={panel}"
    )


# ---------------------------------------------------------------------------
# PR-2 QA Issue F — sidebar hosts the search field, no "아카이브" heading.
# ---------------------------------------------------------------------------


def test_sidebar_has_search_input_and_no_title(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    sidebar_match = re.search(
        r'<aside class="mb-sidebar"[\s\S]*?</aside>', html
    )
    assert sidebar_match, "sidebar <aside> not rendered"
    sidebar = sidebar_match.group(0)
    # Search input lives inside the sidebar now.
    assert 'data-search-input' in sidebar
    assert 'placeholder="아카이브 검색"' in sidebar
    # The "아카이브" sidebar title was removed in PR-2 QA.
    assert "mb-sidebar-title" not in sidebar
    # Close button is always in the DOM; responsive.css surfaces it below 768px.
    assert 'class="mb-sidebar-close"' in sidebar


def test_header_no_longer_embeds_search_form(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    header_match = re.search(r'<header class="mb-header">[\s\S]*?</header>', html)
    assert header_match, "header not rendered"
    header = header_match.group(0)
    assert 'class="mb-search"' not in header, (
        "header should no longer embed the archive search form"
    )
    # Hamburger stays in the header.
    assert 'class="mb-hamburger"' in header


def test_backdrop_div_rendered_hidden_by_default(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    assert 'class="mb-backdrop"' in html
    # Rendered with the ``hidden`` attribute so desktop + first-load states
    # show no dim overlay until sidebar.js opens the drawer on mobile.
    assert re.search(r'class="mb-backdrop"[^>]*\bhidden\b', html)
