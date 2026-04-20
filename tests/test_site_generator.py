"""F2 — site generator: 6-tab structure, 15 cards/tab, country indicator,
source link validity, original headline preserved in source section.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from morning_brief.site.site_generator import generate_site
from tests._site_fixtures import make_full_briefing, make_sceep_map


@pytest.fixture
def site_output(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=15)
    sceep = make_sceep_map(briefing)
    index_path = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
        sceep_by_cluster=sceep,
    )
    return tmp_path, index_path, briefing, ki_map


def _panel_html(html: str, slug: str) -> str:
    m = re.search(
        rf'<section class="mb-tab-panel"\s+id="panel-{slug}"[\s\S]*?</section>',
        html,
    )
    assert m, f"panel-{slug} not found in html"
    return m.group(0)


def test_six_tab_panels_rendered(site_output):
    _, index_path, _, _ = site_output
    html = index_path.read_text(encoding="utf-8")
    for slug in ("macro", "fnb", "beauty", "fashion", "lifestyle", "consumer"):
        assert f'id="panel-{slug}"' in html, f"missing panel-{slug}"


def test_macro_tab_is_first(site_output):
    _, index_path, _, _ = site_output
    html = index_path.read_text(encoding="utf-8")
    # First tab button in <nav class="mb-tabs"> must be MacroTrends
    # (PR-2 QA Issue D: displayed as "매크로 트렌드").
    nav_match = re.search(r'<nav class="mb-tabs"[\s\S]*?</nav>', html)
    assert nav_match
    nav = nav_match.group(0)
    first_btn = re.search(r'data-tab-target="([^"]+)"', nav)
    assert first_btn is not None
    assert first_btn.group(1) == "macro"
    # UI label must be the post-QA "매크로 트렌드", never the retired "거시매크로".
    assert "매크로 트렌드" in nav
    assert "거시매크로" not in nav


def test_fifteen_cards_per_tab(site_output):
    _, index_path, _, _ = site_output
    html = index_path.read_text(encoding="utf-8")
    for slug in ("macro", "fnb", "beauty", "fashion", "lifestyle", "consumer"):
        panel = _panel_html(html, slug)
        count = panel.count('<article class="mb-card"')
        assert count == 15, f"panel {slug}: expected 15 cards, got {count}"


def test_country_indicator_present(site_output):
    _, index_path, _, _ = site_output
    html = index_path.read_text(encoding="utf-8")
    # At least one card per supported language should render its ISO3 code.
    for iso3 in ("KOR", "USA", "JPN", "CHN", "ESP"):
        assert f"({iso3})" in html, f"missing country indicator {iso3}"


def test_source_link_is_valid_and_opens_new_tab(site_output):
    _, index_path, _, _ = site_output
    html = index_path.read_text(encoding="utf-8")
    # Every <a> that lives inside .mb-card-source must have target=_blank.
    links = re.findall(
        r'<footer class="mb-card-source">[\s\S]*?</footer>',
        html,
    )
    assert links, "no source footers rendered"
    for footer in links[:20]:  # sample first 20
        if "<a " in footer:
            assert 'target="_blank"' in footer
            assert 'rel="noopener noreferrer"' in footer


def test_original_headline_preserved_in_source_section(site_output):
    _, index_path, briefing, ki_map = site_output
    html = index_path.read_text(encoding="utf-8")
    # Pick a known macro article; its original headline is assigned in the fixture.
    macro_item = briefing.sections["MacroTrends"][0]
    expected_orig = ki_map[macro_item.cluster_id].article_bundle[0].title
    assert expected_orig in html


def test_index_and_archive_day_exist(site_output):
    out, index_path, _, _ = site_output
    assert index_path.exists()
    assert (out / "archive" / "2026" / "04" / "18.html").exists()
    assert (out / "archive" / "2026" / "04" / "18.json").exists()


def test_static_assets_copied(site_output):
    out, _, _, _ = site_output
    for asset in (
        "static/css/base.css",
        "static/css/card.css",
        "static/css/print.css",
        "static/js/tabs.js",
        "static/js/search.js",
    ):
        assert (out / asset).exists(), f"missing asset {asset}"
