"""F5 — archive/YYYY/MM/DD.html path structure + sidebar tree reflects contents."""

from __future__ import annotations

from pathlib import Path

from morning_brief.site.site_generator import (
    _build_sidebar_tree,
    generate_site,
)
from tests._site_fixtures import make_full_briefing


def test_archive_path_structure(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    assert (tmp_path / "archive" / "2026" / "04" / "18.html").exists()
    assert (tmp_path / "archive" / "2026" / "04" / "18.json").exists()


def test_sidebar_tree_empty_root(tmp_path: Path):
    assert _build_sidebar_tree(tmp_path / "no-archive") == {}


def test_sidebar_tree_reflects_archive(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
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
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2025-12-31",
        key_issues_by_cluster_id=ki_map,
    )
    tree = _build_sidebar_tree(tmp_path / "archive")
    assert set(tree.keys()) == {"2025", "2026"}
    assert tree["2026"]["04"] == ["17", "18"]
    assert tree["2025"]["12"] == ["31"]


def test_sidebar_rendered_in_index_html(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-17",
        key_issues_by_cluster_id=ki_map,
    )
    idx = generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    html = idx.read_text(encoding="utf-8")
    # Both dates appear in the sidebar links.
    assert "archive/2026/04/18.html" in html
    assert "archive/2026/04/17.html" in html


def test_invalid_date_rejected(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    import pytest
    with pytest.raises(ValueError):
        generate_site(
            briefing=briefing,
            output_dir=tmp_path,
            today="2026/04/18",
            key_issues_by_cluster_id=ki_map,
        )
