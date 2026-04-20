"""Build ``search_index.json`` from archived ``archive/YYYY/MM/DD.json`` files.

Keeps the search client-side (per plan §D5 — Pagefind is the long-term
search engine; PR-2 ships a lightweight built-in index so the feature is
end-to-end testable without the extra CLI dep).

Size cap (5 MB): if the flat index exceeds the cap, the function switches
to per-year shards (``search_index_YYYY.json``) and writes a manifest
with ``{"shards": [...]}``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SIZE_CAP_BYTES = 5 * 1024 * 1024  # 5 MB


@dataclass
class SearchRecord:
    """Flat record indexed by search.js."""

    date: str                 # YYYY-MM-DD
    tab: str                  # canonical Category
    card_id: str              # cluster_id
    headline: str
    summary: str
    original_headline: str = ""
    source_name: str = ""
    url: str = ""             # permalink to archive/YYYY/MM/DD.html#card-id
    languages: list[str] = field(default_factory=list)


def _iter_archive_json(archive_root: Path):
    """Yield (date_str, path) for each archive/YYYY/MM/DD.json under root."""
    if not archive_root.exists():
        return
    for year_dir in sorted(p for p in archive_root.iterdir() if p.is_dir()):
        for month_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            for json_path in sorted(month_dir.glob("*.json")):
                # Accept DD.json and DD-revN.json; ignore manifests.
                if json_path.stem == "search_index":
                    continue
                # Latest URL always points at DD.html (rev files are fallbacks).
                stem = json_path.stem.split("-rev")[0]
                date_str = f"{year_dir.name}-{month_dir.name}-{stem}"
                yield date_str, json_path


def _records_from_briefing_json(date_str: str, data: dict[str, Any]) -> list[SearchRecord]:
    """Extract flat search records from a single archived briefing JSON."""
    records: list[SearchRecord] = []
    sections = data.get("sections") or {}
    cards_meta = data.get("cards_meta") or {}  # card_id -> extra metadata
    year, month, day = date_str.split("-")
    archive_html = f"archive/{year}/{month}/{day}.html"
    for tab, items in sections.items():
        for bi in items or []:
            card_id = bi.get("cluster_id", "")
            meta = cards_meta.get(card_id, {}) if isinstance(cards_meta, dict) else {}
            records.append(
                SearchRecord(
                    date=date_str,
                    tab=tab,
                    card_id=card_id,
                    headline=bi.get("title_ko", ""),
                    summary=bi.get("summary_ko", ""),
                    original_headline=meta.get("original_headline", ""),
                    source_name=meta.get("source_name", ""),
                    url=f"{archive_html}#card-{card_id}",
                    languages=meta.get("languages", []),
                )
            )
    return records


def build(archive_root: Path, output_path: Path | None = None) -> Path:
    """Walk the archive, build records, and write search_index.json.

    Returns the path of the primary index file written (the flat index,
    or the manifest when sharding is activated).
    """
    archive_root = Path(archive_root)
    if output_path is None:
        output_path = archive_root.parent / "search_index.json"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_records: list[SearchRecord] = []
    per_year: dict[str, list[SearchRecord]] = {}
    for date_str, json_path in _iter_archive_json(archive_root):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        recs = _records_from_briefing_json(date_str, data)
        all_records.extend(recs)
        per_year.setdefault(date_str[:4], []).extend(recs)

    flat = {"records": [asdict(r) for r in all_records]}
    serialized = json.dumps(flat, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) <= SIZE_CAP_BYTES:
        _atomic_write_text(output_path, serialized)
        return output_path

    # Sharded: write per_year files + manifest.
    shards: list[str] = []
    for year, records in sorted(per_year.items()):
        shard_path = output_path.parent / f"search_index_{year}.json"
        payload = json.dumps(
            {"records": [asdict(r) for r in records]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        _atomic_write_text(shard_path, payload)
        shards.append(shard_path.name)
    manifest = json.dumps({"shards": shards}, ensure_ascii=False)
    _atomic_write_text(output_path, manifest)
    return output_path


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
