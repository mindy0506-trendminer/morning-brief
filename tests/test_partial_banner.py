"""F9 — partial-build banner rendered when ``partial_banner_reason`` set."""

from __future__ import annotations

from pathlib import Path

from morning_brief.site.site_generator import generate_site
from tests._site_fixtures import make_full_briefing


def test_banner_rendered_when_reason_provided(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
        partial_banner_reason="Call B 타임아웃",
    )
    html = idx.read_text(encoding="utf-8")
    assert "mb-partial-banner" in html
    assert "Call B 타임아웃" in html
    assert "부분 브리핑" in html


def test_banner_omitted_by_default(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    assert "mb-partial-banner" not in html
    assert "부분 브리핑" not in html
