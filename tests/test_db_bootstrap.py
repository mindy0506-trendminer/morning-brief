"""Acceptance tests for db bootstrap and basic DAO behaviour."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from morning_brief.db import bootstrap, is_warmup_phase


_ALL_TABLES = {
    "articles",
    "entity_history",
    "clusters",
    "cluster_members",
    "runs",
    "briefed_articles",
}


def _table_names(conn) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {row["name"] for row in rows}


class TestBootstrap:
    def test_creates_all_tables(self, tmp_path: Path):
        """bootstrap() on a fresh path creates all 6 expected tables."""
        db_path = tmp_path / "sub" / "briefing.db"
        conn = bootstrap(db_path)
        assert _table_names(conn) == _ALL_TABLES
        conn.close()

    def test_idempotent(self, tmp_path: Path):
        """Calling bootstrap() twice on the same path raises no error."""
        db_path = tmp_path / "briefing.db"
        conn1 = bootstrap(db_path)
        conn1.close()
        conn2 = bootstrap(db_path)
        assert _table_names(conn2) == _ALL_TABLES
        conn2.close()

    def test_creates_parent_dirs(self, tmp_path: Path):
        """bootstrap() creates intermediate directories if they do not exist."""
        db_path = tmp_path / "a" / "b" / "c" / "briefing.db"
        conn = bootstrap(db_path)
        conn.close()
        assert db_path.exists()


class TestWarmupPhase:
    def test_empty_db_is_warmup(self, tmp_path: Path):
        """is_warmup_phase() returns True for an empty entity_history table."""
        conn = bootstrap(tmp_path / "briefing.db")
        today = datetime.now(timezone.utc)
        assert is_warmup_phase(conn, today) is True
        conn.close()

    def test_old_entity_not_warmup(self, tmp_path: Path):
        """is_warmup_phase() returns False when oldest entity is more than 7 days ago."""
        from datetime import timedelta
        from morning_brief.db import upsert_entity_history

        conn = bootstrap(tmp_path / "briefing.db")
        today = datetime.now(timezone.utc)
        old_time = today - timedelta(days=10)

        upsert_entity_history(conn, "brand_a", "Brand A", "article-1", old_time)
        assert is_warmup_phase(conn, today) is False
        conn.close()

    def test_recent_entity_is_warmup(self, tmp_path: Path):
        """is_warmup_phase() returns True when oldest entity is within 7 days."""
        from datetime import timedelta
        from morning_brief.db import upsert_entity_history

        conn = bootstrap(tmp_path / "briefing.db")
        today = datetime.now(timezone.utc)
        recent_time = today - timedelta(days=3)

        upsert_entity_history(conn, "brand_b", "Brand B", "article-2", recent_time)
        assert is_warmup_phase(conn, today) is True
        conn.close()
