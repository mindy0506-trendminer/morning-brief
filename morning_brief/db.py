"""SQLite schema bootstrap and DAO helpers for morning_brief."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from morning_brief.models import Article, Cluster

DEFAULT_DB_PATH = Path(".omc/state/briefing/briefing.db")


def bootstrap(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database and apply schema idempotently."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    _apply_migrations(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id              TEXT PRIMARY KEY,
            canonical_url   TEXT UNIQUE NOT NULL,
            title           TEXT,
            source_name     TEXT,
            source_type     TEXT,
            lang            TEXT,
            category        TEXT,
            published_at    TEXT,
            raw_summary     TEXT,
            enriched_text   TEXT,
            fetched_at      TEXT,
            company_tags    TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS entity_history (
            entity_norm         TEXT PRIMARY KEY,
            entity_text         TEXT NOT NULL,
            first_seen_at       TEXT NOT NULL,
            last_seen_at        TEXT NOT NULL,
            total_occurrences   INTEGER NOT NULL DEFAULT 0,
            article_ids_json    TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS clusters (
            id                      TEXT PRIMARY KEY,
            run_id                  TEXT,
            category                TEXT NOT NULL,
            canonical_entity_ko     TEXT NOT NULL,
            primary_entity          TEXT NOT NULL,
            is_cross_lingual_merge  INTEGER NOT NULL DEFAULT 0,
            diffusion_score         REAL NOT NULL,
            novelty_score           REAL NOT NULL,
            combined_score          REAL NOT NULL,
            created_at              TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cluster_members (
            cluster_id  TEXT NOT NULL,
            article_id  TEXT NOT NULL,
            PRIMARY KEY (cluster_id, article_id)
        );

        CREATE TABLE IF NOT EXISTS runs (
            id                      TEXT PRIMARY KEY,
            started_at              TEXT NOT NULL,
            completed_at            TEXT,
            run_duration_seconds    REAL,
            stage_durations_json    TEXT,
            llm_usage_json          TEXT,
            schema_version          TEXT,
            notes                   TEXT
        );
        """
    )
    conn.commit()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply idempotent in-place schema migrations.

    Current migrations:
      - Add ``articles.company_tags`` (TEXT, JSON-encoded list, default '[]')
        for DBs bootstrapped before PR-1. ``PRAGMA table_info`` is consulted
        so calls are safe on both fresh and existing DBs.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
    if "company_tags" not in cols:
        conn.execute(
            "ALTER TABLE articles ADD COLUMN company_tags TEXT NOT NULL DEFAULT '[]'"
        )
    conn.commit()


# -------- DAO helpers --------


def upsert_article(conn: sqlite3.Connection, article: Article) -> None:
    """Insert or replace an article row (keyed on canonical_url or id).

    Uses ``INSERT OR REPLACE`` so that either the primary-key (``id``) or the
    UNIQUE constraint on ``canonical_url`` can trigger a refresh. This keeps
    dry-run fixture reloads idempotent even when an earlier run persisted a
    row with the same id but a different canonical_url.
    """
    company_tags_json = json.dumps(
        [tag.model_dump(by_alias=True) for tag in article.company_tags],
        ensure_ascii=False,
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO articles
            (id, canonical_url, title, source_name, source_type, lang,
             category, published_at, raw_summary, enriched_text, fetched_at,
             company_tags)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article.id,
            article.canonical_url,
            article.title,
            article.source_name,
            article.source_type,
            article.language,
            article.category,
            article.published_at.isoformat(),
            article.raw_summary,
            article.enriched_text,
            article.fetched_at.isoformat(),
            company_tags_json,
        ),
    )
    conn.commit()


def upsert_entity_history(
    conn: sqlite3.Connection,
    entity_norm: str,
    entity_text: str,
    article_id: str,
    now: datetime,
) -> None:
    """Insert or update entity_history: set first_seen_at if new, else update last_seen_at, increment count, append article_id."""
    now_iso = now.isoformat()
    existing = conn.execute(
        "SELECT article_ids_json, total_occurrences FROM entity_history WHERE entity_norm = ?",
        (entity_norm,),
    ).fetchone()

    if existing is None:
        conn.execute(
            """
            INSERT INTO entity_history
                (entity_norm, entity_text, first_seen_at, last_seen_at,
                 total_occurrences, article_ids_json)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (entity_norm, entity_text, now_iso, now_iso, json.dumps([article_id])),
        )
    else:
        ids: list[str] = json.loads(existing["article_ids_json"])
        if article_id not in ids:
            ids.append(article_id)
        conn.execute(
            """
            UPDATE entity_history
            SET entity_text        = ?,
                last_seen_at       = ?,
                total_occurrences  = total_occurrences + 1,
                article_ids_json   = ?
            WHERE entity_norm = ?
            """,
            (entity_text, now_iso, json.dumps(ids), entity_norm),
        )
    conn.commit()


def insert_cluster(conn: sqlite3.Connection, cluster: Cluster, run_id: str) -> None:
    """Insert (or replace) a cluster row.

    ``INSERT OR REPLACE`` keeps the operation idempotent across dry-runs that
    reuse deterministic cluster IDs (``cluster_0001``, …). In production the
    cluster IDs are UUIDs, so collisions do not occur.
    """
    conn.execute(
        """
        INSERT OR REPLACE INTO clusters
            (id, run_id, category, canonical_entity_ko, primary_entity,
             is_cross_lingual_merge, diffusion_score, novelty_score,
             combined_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cluster.id,
            run_id,
            cluster.category,
            cluster.canonical_entity_ko,
            cluster.primary_entity,
            int(cluster.is_cross_lingual_merge),
            cluster.diffusion_score,
            cluster.novelty_score,
            cluster.combined_score,
            datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        ),
    )
    conn.commit()


def insert_cluster_members(
    conn: sqlite3.Connection, cluster_id: str, article_ids: list[str]
) -> None:
    """Insert cluster membership rows, ignoring duplicates."""
    conn.executemany(
        "INSERT OR IGNORE INTO cluster_members (cluster_id, article_id) VALUES (?, ?)",
        [(cluster_id, aid) for aid in article_ids],
    )
    conn.commit()


def insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    started_at: datetime,
    schema_version: str = "v2",
) -> None:
    """Insert a new run row."""
    conn.execute(
        """
        INSERT INTO runs (id, started_at, schema_version)
        VALUES (?, ?, ?)
        """,
        (run_id, started_at.isoformat(), schema_version),
    )
    conn.commit()


def update_run_completed(
    conn: sqlite3.Connection,
    run_id: str,
    completed_at: datetime,
    stage_durations: dict,
    llm_usage: dict,
    notes: str = "",
) -> None:
    """Mark a run as completed with timing and usage metadata."""
    started_row = conn.execute(
        "SELECT started_at FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    run_duration: float | None = None
    if started_row:
        started = datetime.fromisoformat(started_row["started_at"])
        run_duration = (completed_at - started).total_seconds()

    conn.execute(
        """
        UPDATE runs
        SET completed_at          = ?,
            run_duration_seconds  = ?,
            stage_durations_json  = ?,
            llm_usage_json        = ?,
            notes                 = ?
        WHERE id = ?
        """,
        (
            completed_at.isoformat(),
            run_duration,
            json.dumps(stage_durations),
            json.dumps(llm_usage),
            notes,
            run_id,
        ),
    )
    conn.commit()


def query_entity_prior_days(
    conn: sqlite3.Connection, entity_norm: str, today: datetime, days: int = 7
) -> int:
    """Count distinct days in last N days where entity was seen."""
    since = (today - timedelta(days=days)).isoformat()
    row = conn.execute(
        """
        SELECT total_occurrences
        FROM entity_history
        WHERE entity_norm = ?
          AND last_seen_at >= ?
        """,
        (entity_norm, since),
    ).fetchone()
    return row["total_occurrences"] if row else 0


def is_warmup_phase(conn: sqlite3.Connection, today: datetime) -> bool:
    """Return True if DB is empty or oldest entity first_seen_at is within the last 7 days."""
    row = conn.execute(
        "SELECT MIN(first_seen_at) AS oldest FROM entity_history"
    ).fetchone()
    if row is None or row["oldest"] is None:
        return True
    cutoff = (today - timedelta(days=7)).isoformat()
    return row["oldest"] > cutoff
