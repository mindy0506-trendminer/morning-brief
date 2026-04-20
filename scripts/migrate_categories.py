"""One-shot migration: legacy category names -> D10-A canonical names.

Scheduled for deletion ~30 days after PR-1 merges (plan v2 §F/U-6).

This script is idempotent: running it multiple times is safe. Rows that
already carry a canonical value are skipped. Fixture files that no longer
contain legacy strings are left untouched.

Legacy → canonical mapping (plan v2 §D10-A + PR-2 browser QA Issue C):
    Food         -> 식음료
    F&B          -> 식음료          (intermediate canonical state; 식음료 replaces it)
    Beauty       -> 뷰티
    Fashion      -> 패션
    Living       -> 라이프스타일
    Hospitality  -> 라이프스타일   (Hospitality collapses into 라이프스타일)

Scope:
  1. briefing.db   — UPDATE clusters.category + articles.category
  2. fixtures      — rewrite tests/fixtures/*.json in place

Usage:
    python scripts/migrate_categories.py               # migrate real DB + fixtures
    python scripts/migrate_categories.py --dry-run     # report-only, no writes
    python scripts/migrate_categories.py --db PATH     # alternate DB path
    python scripts/migrate_categories.py --fixtures DIR  # alternate fixtures dir
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


# Mapping used everywhere. Keep this as the single source of truth; callers
# import it from this module for tests.
LEGACY_TO_CANONICAL: dict[str, str] = {
    "Food": "식음료",
    # PR-2 QA Issue C: intermediate "F&B" canonical state is now also
    # rewritten to "식음료" so running the migration twice (or against a DB
    # that already saw the first rename) still upgrades cleanly.
    "F&B": "식음료",
    "Beauty": "뷰티",
    "Fashion": "패션",
    "Living": "라이프스타일",
    "Hospitality": "라이프스타일",
}


# ---------------------------------------------------------------------------
# DB migration
# ---------------------------------------------------------------------------


def migrate_db(db_path: Path, dry_run: bool = False) -> dict[str, int]:
    """Rewrite legacy category values in briefing.db.

    Returns a counter dict:
      {"clusters_updated": N, "articles_updated": M, "skipped_canonical": K}
    """
    counts = {
        "clusters_updated": 0,
        "articles_updated": 0,
        "skipped_canonical": 0,
    }

    if not db_path.exists():
        # No DB yet — this is a legitimate fresh-install path, not an error.
        return counts

    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row

        for table in ("clusters", "articles"):
            # Table may not exist on a partially-bootstrapped DB.
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                continue

            rows = conn.execute(
                f"SELECT rowid, category FROM {table} WHERE category IS NOT NULL"
            ).fetchall()

            for row in rows:
                cat = row["category"]
                if cat in LEGACY_TO_CANONICAL:
                    new_cat = LEGACY_TO_CANONICAL[cat]
                    if not dry_run:
                        conn.execute(
                            f"UPDATE {table} SET category = ? WHERE rowid = ?",
                            (new_cat, row["rowid"]),
                        )
                    counts[f"{table}_updated"] += 1
                elif cat in LEGACY_TO_CANONICAL.values():
                    counts["skipped_canonical"] += 1
                # Anything else (None, Uncategorized, etc.) we leave alone.

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return counts


# ---------------------------------------------------------------------------
# Fixture rewrite
# ---------------------------------------------------------------------------


def _rewrite_in_json(obj: Any) -> tuple[Any, int]:
    """Recursively replace legacy category strings in a JSON-decoded object.

    Rewrites:
      - ``{"category": "Food"}``                     -> ``"category": "식음료"``
      - ``{"category_confirmed": "Fashion"}``        -> ``"category_confirmed": "패션"``
      - ``{"sections": {"Food": [...]}}``            -> keys renamed

    Returns (new_object, replacements_made).
    """
    replaced = 0

    if isinstance(obj, dict):
        new: dict[str, Any] = {}
        for key, value in obj.items():
            # Rename dict keys that are legacy category names, but only when
            # they appear in a known category-keyed container. The safe rule
            # is: if the *key* is a legacy category string, rewrite it.
            new_key = key
            if isinstance(key, str) and key in LEGACY_TO_CANONICAL:
                new_key = LEGACY_TO_CANONICAL[key]
                replaced += 1

            new_value, sub_replaced = _rewrite_in_json(value)
            replaced += sub_replaced

            # Additionally, rewrite known category-valued fields.
            if (
                isinstance(key, str)
                and key in {"category", "category_confirmed", "category_hint"}
                and isinstance(new_value, str)
                and new_value in LEGACY_TO_CANONICAL
            ):
                new_value = LEGACY_TO_CANONICAL[new_value]
                replaced += 1

            new[new_key] = new_value
        return new, replaced

    if isinstance(obj, list):
        new_list: list[Any] = []
        for item in obj:
            new_item, sub_replaced = _rewrite_in_json(item)
            replaced += sub_replaced
            new_list.append(new_item)
        return new_list, replaced

    # Primitive values other than strings are untouched.
    return obj, replaced


def migrate_fixtures(fixtures_dir: Path, dry_run: bool = False) -> dict[str, int]:
    """Rewrite legacy category strings in every *.json under fixtures_dir.

    Idempotent: files that have nothing to rewrite are not re-written.
    """
    counts = {
        "files_updated": 0,
        "files_unchanged": 0,
        "replacements_total": 0,
    }

    if not fixtures_dir.exists():
        return counts

    for path in sorted(fixtures_dir.rglob("*.json")):
        try:
            original_text = path.read_text(encoding="utf-8")
            data = json.loads(original_text)
        except (json.JSONDecodeError, OSError):
            # Leave malformed or unreadable files alone.
            continue

        new_data, replacements = _rewrite_in_json(data)

        if replacements == 0:
            counts["files_unchanged"] += 1
            continue

        counts["files_updated"] += 1
        counts["replacements_total"] += replacements

        if dry_run:
            continue

        new_text = json.dumps(new_data, ensure_ascii=False, indent=2)
        # Preserve trailing newline behaviour of the original file.
        if original_text.endswith("\n"):
            new_text += "\n"
        path.write_text(new_text, encoding="utf-8")

    return counts


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy category values (Food/Beauty/Fashion/Living/"
            "Hospitality) to the D10-A canonical set."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(".omc/state/briefing/briefing.db"),
        help="Path to briefing.db (default: .omc/state/briefing/briefing.db)",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures"),
        help="Fixture directory to rewrite (default: tests/fixtures)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned changes without writing to DB or files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    print(f"[migrate_categories] db={args.db} fixtures={args.fixtures} dry_run={args.dry_run}")

    db_counts = migrate_db(args.db, dry_run=args.dry_run)
    fx_counts = migrate_fixtures(args.fixtures, dry_run=args.dry_run)

    print(
        "[migrate_categories] DB: {0} cluster rows updated, "
        "{1} article rows updated, {2} already-canonical rows skipped.".format(
            db_counts["clusters_updated"],
            db_counts["articles_updated"],
            db_counts["skipped_canonical"],
        )
    )
    print(
        "[migrate_categories] Fixtures: {0} files updated, "
        "{1} files unchanged, {2} legacy strings rewritten.".format(
            fx_counts["files_updated"],
            fx_counts["files_unchanged"],
            fx_counts["replacements_total"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
