"""Static-site generator — plan v2 §C.

Writes::

    out/
      index.html                 # copy of today's archive page (entry point)
      archive/YYYY/MM/DD.html    # permanent-URL archive page
      archive/YYYY/MM/DD.json    # serialized briefing (for rehydrate + search)
      search_index.json          # flat search index (see search_index.py)
      static/                    # copied on first run (css + js)

Atomic-write contract (plan v2 §C13):
    1. Every file is written as ``<path>.tmp`` first.
    2. ``os.replace(path.tmp, path)`` moves it into place (atomic on POSIX
       and on Windows for the same volume).
    3. If ``archive/YYYY/MM/DD.html`` already exists and the content
       differs, the new content goes to ``DD-rev1.html`` (``-rev2`` …) so
       permanent URLs are never overwritten. A copy of the latest content
       still lands at ``DD.html`` so the canonical URL always reflects the
       most recent publication.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import asdict, is_dataclass
from datetime import date as _date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from morning_brief.models import KeyIssue, LLMBriefing, SceepDimension
from morning_brief.site.renderer_adapter import TAB_ORDER, build_template_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

_PKG_DIR = Path(__file__).parent
_TEMPLATES_DIR = _PKG_DIR / "templates"
_STATIC_SRC = _PKG_DIR / "static"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj: Any) -> None:
    """Serialize ``obj`` to UTF-8 JSON and replace ``path`` atomically."""
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
    _atomic_write_text(path, text)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_html_with_collision(path: Path, html: str) -> Path:
    """Write HTML to ``path`` atomically; create ``-revN`` sibling on content diff.

    Always returns the path of the final canonical HTML (i.e. ``path`` —
    the latest content is copied there even when a revision snapshot was
    created, so the permanent URL always serves the newest version).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    new_bytes = html.encode("utf-8")
    if path.exists():
        existing = path.read_bytes()
        if _hash_bytes(existing) != _hash_bytes(new_bytes):
            # Preserve the previous canonical content as DD-revN.html.
            rev_path = _next_rev_path(path, existing)
            _atomic_write_bytes(rev_path, existing)
            logger.warning(
                "archive collision: wrote prior content to %s before updating %s",
                rev_path.name,
                path.name,
            )
    _atomic_write_bytes(path, new_bytes)
    return path


def _next_rev_path(canonical: Path, existing_bytes: bytes) -> Path:
    """Return a free ``DD-revN.html`` sibling path for the given canonical file.

    Skips any ``-revN`` that already exists with byte-identical content to
    the previous canonical file (idempotent re-runs).
    """
    parent = canonical.parent
    stem = canonical.stem
    suffix = canonical.suffix
    n = 1
    existing_hash = _hash_bytes(existing_bytes)
    while True:
        rev = parent / f"{stem}-rev{n}{suffix}"
        if not rev.exists():
            return rev
        if _hash_bytes(rev.read_bytes()) == existing_hash:
            # The previous canonical is already preserved at this rev slot.
            return rev
        n += 1


# ---------------------------------------------------------------------------
# Sidebar tree
# ---------------------------------------------------------------------------


def _build_sidebar_tree(archive_root: Path) -> dict[str, dict[str, list[str]]]:
    """Walk ``archive/`` and return ``{year: {month: [days]}}``."""
    tree: dict[str, dict[str, list[str]]] = {}
    if not archive_root.exists():
        return tree
    for year_dir in archive_root.iterdir():
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = year_dir.name
        months: dict[str, list[str]] = {}
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            days = sorted(
                {p.stem.split("-rev")[0] for p in month_dir.glob("*.html")}
            )
            if days:
                months[month_dir.name] = days
        if months:
            tree[year] = months
    return tree


# ---------------------------------------------------------------------------
# Static asset staging
# ---------------------------------------------------------------------------


def _copy_static_tree(output_dir: Path) -> None:
    """Mirror ``static/`` into ``output_dir/static/`` (idempotent).

    Walks the package static tree and copies each file whose mtime is
    newer than the destination's (or which is missing). Avoids
    ``shutil.rmtree`` so concurrent reads on Windows don't trigger a
    ``PermissionError`` mid-rewrite.
    """
    dst_root = output_dir / "static"
    dst_root.mkdir(parents=True, exist_ok=True)
    for src_file in _STATIC_SRC.rglob("*"):
        if src_file.is_dir():
            continue
        rel = src_file.relative_to(_STATIC_SRC)
        dst_file = dst_root / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            if (
                dst_file.exists()
                and dst_file.stat().st_mtime >= src_file.stat().st_mtime
                and dst_file.stat().st_size == src_file.stat().st_size
            ):
                continue
        except OSError:
            pass
        shutil.copy2(src_file, dst_file)


# ---------------------------------------------------------------------------
# Context → HTML
# ---------------------------------------------------------------------------


def _render_page(
    env: Environment,
    *,
    template_name: str,
    context: dict[str, Any],
    static_prefix: str,
    archive_prefix: str,
) -> str:
    tmpl = env.get_template(template_name)
    return tmpl.render(
        static_prefix=static_prefix,
        archive_prefix=archive_prefix,
        **context,
    )


# ---------------------------------------------------------------------------
# Briefing JSON sidecar
# ---------------------------------------------------------------------------


def _briefing_to_archive_json(
    briefing: LLMBriefing,
    key_issues_by_cluster_id: dict[str, KeyIssue],
    sceep_by_cluster: dict[str, list[SceepDimension]] | None,
) -> dict[str, Any]:
    """Produce the schema stored at ``archive/YYYY/MM/DD.json``.

    Shape is intentionally loose: it is a serialization of the briefing
    plus metadata the search indexer needs (source names, original
    headlines, languages) — exactly what the client side search wants.
    """
    cards_meta: dict[str, dict[str, Any]] = {}
    for cat in TAB_ORDER:
        for bi in briefing.sections.get(cat, []) or []:
            ki = key_issues_by_cluster_id.get(bi.cluster_id)
            primary = ki.article_bundle[0] if ki and ki.article_bundle else None
            cards_meta[bi.cluster_id] = {
                "category": cat,
                "source_name": primary.source_name if primary else "",
                "source_url": (
                    primary.canonical_url or primary.url if primary else ""
                ),
                "original_headline": primary.title if primary else "",
                "languages": [a.language for a in (ki.article_bundle if ki else [])],
                "sceep_dimensions": list(
                    (sceep_by_cluster or {}).get(bi.cluster_id, [])
                ),
            }
    return {
        "schema_version": briefing.schema_version,
        "exec_summary_ko": list(briefing.exec_summary_ko),
        "sections": {
            cat: [
                {
                    "cluster_id": bi.cluster_id,
                    "title_ko": bi.title_ko,
                    "summary_ko": bi.summary_ko,
                    "is_paywalled": bi.is_paywalled,
                }
                for bi in (briefing.sections.get(cat, []) or [])
            ]
            for cat in TAB_ORDER
            if briefing.sections.get(cat)
        },
        "insight_box_ko": briefing.insight_box_ko,
        "cards_meta": cards_meta,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_site(
    briefing: LLMBriefing,
    output_dir: Path,
    *,
    today: _date | str,
    key_issues_by_cluster_id: dict[str, KeyIssue] | None = None,
    sceep_by_cluster: dict[str, list[SceepDimension]] | None = None,
    archive_mode: bool = True,
    partial_banner_reason: str | None = None,
) -> Path:
    """Generate the static site for a single briefing.

    Parameters
    ----------
    briefing:
        Call B output.
    output_dir:
        Root of the generated site (``out/`` by default).
    today:
        ``YYYY-MM-DD`` string or ``datetime.date``.
    key_issues_by_cluster_id:
        Optional metadata (source names, original headlines, ...). When
        omitted the card source footer falls back to empty strings — the
        site still renders.
    sceep_by_cluster:
        ``cluster_id -> [SceepDimension, ...]`` map from ``macro_tagger``.
        Only cards on the MacroTrends tab will render chips.
    archive_mode:
        When True (default) writes ``archive/YYYY/MM/DD.html`` and the
        JSON sidecar. When False only ``index.html`` is produced (useful
        for ad-hoc previews).
    partial_banner_reason:
        If set, the exit-code-6 banner is injected at the top of the page.

    Returns
    -------
    Path to ``output_dir/index.html`` (the "latest" entry point).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    today_iso = today.isoformat() if isinstance(today, _date) else str(today)
    if not _DATE_RE.match(today_iso):
        raise ValueError(f"today must be YYYY-MM-DD, got {today_iso!r}")
    year, month, day = today_iso.split("-")

    key_issues_by_cluster_id = key_issues_by_cluster_id or {}
    sceep_by_cluster = dict(sceep_by_cluster or {})

    archive_root = output_dir / "archive"
    archive_dir = archive_root / year / month
    archive_html_path = archive_dir / f"{day}.html"
    archive_json_path = archive_dir / f"{day}.json"
    index_html_path = output_dir / "index.html"

    # Copy static assets early so rel links resolve immediately.
    _copy_static_tree(output_dir)

    # Build the sidebar tree BEFORE writing so today's page sees itself
    # only if a prior run already materialized it. We then rebuild once
    # more after the write so the sidebar on the freshly-written page
    # reflects the new day too.
    sidebar_tree = _build_sidebar_tree(archive_root)
    sidebar_tree.setdefault(year, {}).setdefault(month, [])
    if day not in sidebar_tree[year][month]:
        sidebar_tree[year][month] = sorted(sidebar_tree[year][month] + [day])

    context = build_template_context(
        briefing=briefing,
        key_issues_by_cluster_id=key_issues_by_cluster_id,
        today_iso=today_iso,
        sidebar_tree=sidebar_tree,
        partial_banner_reason=partial_banner_reason,
        sceep_by_cluster=sceep_by_cluster,
    )

    env = _build_env()

    # Archive page — rel prefixes walk back to the site root.
    archive_html = _render_page(
        env,
        template_name="archive_day.html",
        context=context,
        static_prefix="../../../static/",
        archive_prefix="../../",
    )

    # Index (today) — assets live at ./static/; archive at ./archive/.
    index_html = _render_page(
        env,
        template_name="index.html",
        context=context,
        static_prefix="static/",
        archive_prefix="archive/",
    )

    if archive_mode:
        _write_html_with_collision(archive_html_path, archive_html)
        atomic_write_json(
            archive_json_path,
            _briefing_to_archive_json(
                briefing, key_issues_by_cluster_id, sceep_by_cluster
            ),
        )

    _atomic_write_text(index_html_path, index_html)

    # Rebuild the search index after the write so today's records are
    # included. Imported here to avoid a circular import.
    from morning_brief.site import search_index

    search_index.build(archive_root, output_dir / "search_index.json")

    return index_html_path


# Convenience helper kept public so tests can exercise the collision path
# without standing up the whole generator.
def write_archive_html(path: Path, html: str) -> Path:
    """Write archive HTML with atomic + revN collision semantics."""
    return _write_html_with_collision(path, html)
