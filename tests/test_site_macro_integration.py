"""End-to-end check: SCTEEP badges actually reach MacroTab cards.

Exercises the full summarizer → macro_tagger → site_generator bridge wired
in PR-3 Task 1. These tests do NOT hit Anthropic — they rely on the dry-run
deterministic fallback inside ``macro_tagger.tag_macro_clusters_dry_run``.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from morning_brief import collector, selector, summarizer
from morning_brief.db import bootstrap, insert_run
from morning_brief.site.site_generator import generate_site


_SCEEP_SPAN_RE = re.compile(r'<span class="mb-sceep mb-sceep-[a-z]+"')


def _run_dry_pipeline_and_render(tmp_path: Path) -> str:
    db_path = tmp_path / "briefing.db"
    conn = bootstrap(db_path)
    now = datetime(2026, 4, 18, 7, 0, 0)
    run_id = f"2026-04-18-070000-{id(tmp_path)}"
    insert_run(conn, run_id, now)

    articles, _ = collector.collect(conn, now, dry_run=True)
    scored = selector.select(conn, articles, now, dry_run=True)
    articles_by_id = {a.id: a for a in articles}
    briefing, key_issues_all, _, _ = summarizer.run_summarizer(
        conn=conn,
        scored_candidates=scored,
        articles_by_id=articles_by_id,
        today=now,
        run_id=run_id,
        dry_run=True,
        api_key="dry-run-key",
    )
    ki_by_id = {ki.cluster_id: ki for ki in key_issues_all}
    output_dir = tmp_path / "out"
    generate_site(
        briefing=briefing,
        output_dir=output_dir,
        today=now.date(),
        key_issues_by_cluster_id=ki_by_id,
    )
    conn.close()
    return (output_dir / "index.html").read_text(encoding="utf-8")


def _panel(html: str, slug: str) -> str:
    m = re.search(
        rf'<section class="mb-tab-panel"\s+id="panel-{slug}"[\s\S]*?</section>',
        html,
    )
    assert m, f"panel-{slug} not found in html"
    return m.group(0)


def test_macro_tab_cards_have_sceep_dimensions(tmp_path: Path) -> None:
    """After the full dry-run pipeline, MacroTab cards render SCTEEP chips."""
    html = _run_dry_pipeline_and_render(tmp_path)
    macro = _panel(html, "macro")
    # The template wraps each chip row in mb-sceep-row and each chip in
    # <span class="mb-sceep mb-sceep-{dim}" …>.
    assert "mb-sceep-row" in macro, "no SCTEEP row on MacroTab"
    chips = _SCEEP_SPAN_RE.findall(macro)
    assert len(chips) >= 2, (
        f"expected >= 2 SCTEEP chips on MacroTab, got {len(chips)}"
    )


def test_non_macro_cards_have_no_sceep_badges(tmp_path: Path) -> None:
    """The 5 industry tabs must never render SCTEEP chips."""
    html = _run_dry_pipeline_and_render(tmp_path)
    for slug in ("fnb", "beauty", "fashion", "lifestyle", "consumer"):
        panel = _panel(html, slug)
        assert "mb-sceep-row" not in panel, (
            f"SCTEEP row leaked into industry tab '{slug}'"
        )
        assert not _SCEEP_SPAN_RE.search(panel), (
            f"SCTEEP chip span leaked into industry tab '{slug}'"
        )
