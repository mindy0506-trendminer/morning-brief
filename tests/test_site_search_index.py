"""F7 — search_index.json contains every card record and stays under 5MB."""

from __future__ import annotations

import json
from pathlib import Path

from morning_brief.site import search_index
from morning_brief.site.site_generator import generate_site
from tests._site_fixtures import make_full_briefing


def test_search_index_contains_every_card(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=3)
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    idx_path = tmp_path / "search_index.json"
    assert idx_path.exists()
    data = json.loads(idx_path.read_text(encoding="utf-8"))
    assert "records" in data
    records = data["records"]
    # 6 tabs × 3 cards = 18 records.
    assert len(records) == 18
    # Spot-check schema.
    r0 = records[0]
    for key in ("date", "tab", "card_id", "headline", "summary", "url"):
        assert key in r0, f"missing key {key}"


def test_search_index_url_points_to_archive_with_anchor(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    data = json.loads((tmp_path / "search_index.json").read_text(encoding="utf-8"))
    for rec in data["records"]:
        assert rec["url"].startswith("archive/2026/04/18.html#card-")


def test_search_index_aggregates_across_days(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=2)
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-17",
        key_issues_by_cluster_id=ki_map,
    )
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    data = json.loads((tmp_path / "search_index.json").read_text(encoding="utf-8"))
    dates = {r["date"] for r in data["records"]}
    assert dates == {"2026-04-17", "2026-04-18"}
    # 6 tabs × 2 cards × 2 days = 24 records.
    assert len(data["records"]) == 24


def test_search_index_size_well_under_cap(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=15)
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    size = (tmp_path / "search_index.json").stat().st_size
    assert size < search_index.SIZE_CAP_BYTES
