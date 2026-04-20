"""Tests for scripts/migrate_categories.py (plan v2 §D10-A / PR-1 Task 7).

Covers:
  - Fresh-DB safety: running the script against a non-existent DB path is a no-op.
  - DB migration: legacy category values rewritten to the D10-A canonical set.
  - Idempotency: second run is a no-op (counts reflect zero changes).
  - Fixture rewrite: nested section keys + scalar category_confirmed fields.
  - LEGACY_TO_CANONICAL mapping is the single source of truth.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.migrate_categories import (
    LEGACY_TO_CANONICAL,
    migrate_db,
    migrate_fixtures,
)


# ---------------------------------------------------------------------------
# Mapping integrity
# ---------------------------------------------------------------------------


class TestMappingConstant:
    def test_mapping_is_complete(self):
        # PR-2 QA Issue C added "F&B" as an intermediate legacy token that
        # must also upgrade to "식음료" on re-runs.
        assert set(LEGACY_TO_CANONICAL.keys()) == {
            "Food",
            "F&B",
            "Beauty",
            "Fashion",
            "Living",
            "Hospitality",
        }

    def test_hospitality_collapses_into_lifestyle(self):
        assert LEGACY_TO_CANONICAL["Hospitality"] == "라이프스타일"
        assert LEGACY_TO_CANONICAL["Living"] == "라이프스타일"

    def test_fnb_upgrades_to_korean_canonical(self):
        # PR-2 QA Issue C: F&B → 식음료 rename must be idempotent across runs.
        assert LEGACY_TO_CANONICAL["F&B"] == "식음료"
        assert LEGACY_TO_CANONICAL["Food"] == "식음료"

    def test_targets_are_canonical(self):
        # Every target value must be in the post-QA canonical set.
        canonical = {"식음료", "뷰티", "패션", "라이프스타일", "소비트렌드", "MacroTrends"}
        assert set(LEGACY_TO_CANONICAL.values()) <= canonical


# ---------------------------------------------------------------------------
# DB migration
# ---------------------------------------------------------------------------


def _bootstrap_briefing_schema(db_path: Path) -> sqlite3.Connection:
    """Create just the clusters+articles tables this script touches.

    Mirrors a subset of morning_brief.db._create_tables so this test does not
    depend on that module's full schema (which would pull in all migrations).
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE clusters (
            id                      TEXT PRIMARY KEY,
            category                TEXT NOT NULL,
            canonical_entity_ko     TEXT NOT NULL DEFAULT '',
            created_at              TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE articles (
            id              TEXT PRIMARY KEY,
            canonical_url   TEXT NOT NULL,
            category        TEXT
        );
        """
    )
    conn.commit()
    return conn


class TestDbMigration:
    def test_missing_db_is_noop(self, tmp_path: Path):
        counts = migrate_db(tmp_path / "does-not-exist.db")
        assert counts == {
            "clusters_updated": 0,
            "articles_updated": 0,
            "skipped_canonical": 0,
        }

    def test_rewrites_legacy_values(self, tmp_path: Path):
        db = tmp_path / "briefing.db"
        conn = _bootstrap_briefing_schema(db)
        conn.executemany(
            "INSERT INTO clusters (id, category) VALUES (?, ?)",
            [
                ("c1", "Food"),
                ("c2", "Hospitality"),
                # PR-2 QA Issue C: intermediate "F&B" canonical state is
                # itself a legacy token now that "식음료" is canonical.
                ("c3", "F&B"),
                ("c4", "식음료"),  # already canonical — should be skipped
            ],
        )
        conn.executemany(
            "INSERT INTO articles (id, canonical_url, category) VALUES (?, ?, ?)",
            [
                ("a1", "https://x/1", "Beauty"),
                ("a2", "https://x/2", "Living"),
            ],
        )
        conn.commit()
        conn.close()

        counts = migrate_db(db)
        # c1 Food, c2 Hospitality, c3 F&B all get rewritten.
        assert counts["clusters_updated"] == 3
        assert counts["articles_updated"] == 2
        # Only c4 식음료 is already canonical.
        assert counts["skipped_canonical"] == 1

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        cats = {r["id"]: r["category"] for r in conn.execute("SELECT id, category FROM clusters")}
        assert cats == {
            "c1": "식음료",
            "c2": "라이프스타일",
            "c3": "식음료",
            "c4": "식음료",
        }
        art_cats = {
            r["id"]: r["category"] for r in conn.execute("SELECT id, category FROM articles")
        }
        assert art_cats == {"a1": "뷰티", "a2": "라이프스타일"}
        conn.close()

    def test_idempotent_on_second_run(self, tmp_path: Path):
        db = tmp_path / "briefing.db"
        conn = _bootstrap_briefing_schema(db)
        conn.execute("INSERT INTO clusters (id, category) VALUES ('c1', 'Fashion')")
        conn.commit()
        conn.close()

        first = migrate_db(db)
        assert first["clusters_updated"] == 1

        second = migrate_db(db)
        assert second["clusters_updated"] == 0
        assert second["articles_updated"] == 0
        # Already-canonical row contributes to skipped_canonical on rerun.
        assert second["skipped_canonical"] == 1

    def test_dry_run_leaves_db_untouched(self, tmp_path: Path):
        db = tmp_path / "briefing.db"
        conn = _bootstrap_briefing_schema(db)
        conn.execute("INSERT INTO clusters (id, category) VALUES ('c1', 'Food')")
        conn.commit()
        conn.close()

        counts = migrate_db(db, dry_run=True)
        assert counts["clusters_updated"] == 1

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT category FROM clusters WHERE id = 'c1'").fetchone()
        conn.close()
        # Category stays legacy because dry_run does not write.
        assert row[0] == "Food"


# ---------------------------------------------------------------------------
# Fixture rewrite
# ---------------------------------------------------------------------------


class TestFixtureMigration:
    def test_rewrites_scalar_and_nested_keys(self, tmp_path: Path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        sample_path = fixtures / "sample.json"
        sample_path.write_text(
            json.dumps(
                {
                    "category": "Food",
                    "clusters": [{"category_confirmed": "Fashion"}],
                    "sections": {"Beauty": [1, 2]},
                }
            ),
            encoding="utf-8",
        )

        counts = migrate_fixtures(fixtures)
        assert counts["files_updated"] == 1
        assert counts["replacements_total"] >= 3

        data = json.loads(sample_path.read_text(encoding="utf-8"))
        assert data["category"] == "식음료"
        assert data["clusters"][0]["category_confirmed"] == "패션"
        assert "뷰티" in data["sections"]
        assert "Beauty" not in data["sections"]

    def test_idempotent(self, tmp_path: Path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        (fixtures / "sample.json").write_text(
            json.dumps({"category": "Hospitality"}), encoding="utf-8"
        )

        first = migrate_fixtures(fixtures)
        assert first["files_updated"] == 1

        second = migrate_fixtures(fixtures)
        assert second["files_updated"] == 0
        assert second["replacements_total"] == 0

    def test_missing_fixtures_dir_is_noop(self, tmp_path: Path):
        counts = migrate_fixtures(tmp_path / "no-such-dir")
        assert counts == {
            "files_updated": 0,
            "files_unchanged": 0,
            "replacements_total": 0,
        }

    def test_unchanged_files_not_rewritten(self, tmp_path: Path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        target = fixtures / "sample.json"
        # 식음료 is the post-QA canonical value; a file that already uses it
        # should not be rewritten on subsequent migration runs.
        original = json.dumps({"category": "식음료", "title": "unchanged"})
        target.write_text(original, encoding="utf-8")
        mtime_before = target.stat().st_mtime_ns

        counts = migrate_fixtures(fixtures)
        assert counts["files_updated"] == 0
        assert counts["files_unchanged"] == 1
        # The script short-circuits when nothing to rewrite; mtime stays put.
        assert target.stat().st_mtime_ns == mtime_before
