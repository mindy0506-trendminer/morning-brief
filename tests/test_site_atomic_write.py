"""F4 — atomic writes don't corrupt output; -rev1 created on content diff."""

from __future__ import annotations

from pathlib import Path

from morning_brief.site.site_generator import (
    atomic_write_json,
    generate_site,
    write_archive_html,
)
from tests._site_fixtures import make_full_briefing


def test_tmp_file_cleaned_up(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    # No .tmp files should remain anywhere in the output tree.
    leftover = list(tmp_path.rglob("*.tmp"))
    assert leftover == [], f"stale .tmp files: {leftover}"


def test_second_write_same_content_no_revision(tmp_path: Path):
    briefing, ki_map = make_full_briefing(cards_per_tab=1)
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    generate_site(
        briefing=briefing,
        output_dir=tmp_path,
        today="2026-04-18",
        key_issues_by_cluster_id=ki_map,
    )
    archive_dir = tmp_path / "archive" / "2026" / "04"
    rev_files = list(archive_dir.glob("18-rev*.html"))
    assert rev_files == [], f"unexpected revision files: {rev_files}"


def test_content_diff_creates_rev1(tmp_path: Path):
    archive = tmp_path / "archive" / "2026" / "04"
    archive.mkdir(parents=True)
    canonical = archive / "18.html"

    write_archive_html(canonical, "<html>original</html>")
    assert canonical.read_text(encoding="utf-8") == "<html>original</html>"
    assert not (archive / "18-rev1.html").exists()

    write_archive_html(canonical, "<html>updated</html>")
    assert canonical.read_text(encoding="utf-8") == "<html>updated</html>"
    rev1 = archive / "18-rev1.html"
    assert rev1.exists()
    assert rev1.read_text(encoding="utf-8") == "<html>original</html>"


def test_three_distinct_writes_produce_rev1_rev2(tmp_path: Path):
    archive = tmp_path / "archive" / "2026" / "04"
    archive.mkdir(parents=True)
    canonical = archive / "18.html"

    write_archive_html(canonical, "<html>v1</html>")
    write_archive_html(canonical, "<html>v2</html>")
    write_archive_html(canonical, "<html>v3</html>")

    rev1 = archive / "18-rev1.html"
    rev2 = archive / "18-rev2.html"
    assert rev1.exists() and rev2.exists()
    # rev1 preserves the first version, rev2 preserves the second version.
    assert rev1.read_text(encoding="utf-8") == "<html>v1</html>"
    assert rev2.read_text(encoding="utf-8") == "<html>v2</html>"
    assert canonical.read_text(encoding="utf-8") == "<html>v3</html>"


def test_atomic_write_json_roundtrip(tmp_path: Path):
    p = tmp_path / "sub" / "out.json"
    atomic_write_json(p, {"a": 1, "b": [1, 2, 3], "ko": "한글"})
    import json
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"a": 1, "b": [1, 2, 3], "ko": "한글"}
