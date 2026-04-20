"""CLI entry point for morning_brief.

Subcommands:
  run        — full pipeline (collect → select → summarize → render)
  dry-run    — same pipeline but uses fixture data and mock LLM responses
  rerender   — re-render from persisted call_b_response.json + key_issues.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DB_PATH = Path(".omc/state/briefing/briefing.db")
_RUN_STATE_DIR = Path(".omc/state/briefing/runs")
_DEFAULT_OUTPUT_DIR = Path("out")
_DEFAULT_CALL_A_MODEL = "claude-haiku-4"
_DEFAULT_CALL_B_MODEL = "claude-sonnet-4-6"

# run_id format emitted by _generate_run_id: YYYY-MM-DD-HHMMSS
_RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_run_id(now: datetime) -> str:
    return now.strftime("%Y-%m-%d-%H%M%S")


def _load_env() -> None:
    """Load .env if python-dotenv is installed; silently skip otherwise."""
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]
        load_dotenv(override=True)
    except ImportError:
        pass


def _require_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"ERROR: Required environment variable {key} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


def _env_truthy(name: str) -> bool:
    """Return True if env var ``name`` is a common truthy string."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Full pipeline (shared between `run` and `dry-run`)
# ---------------------------------------------------------------------------


def _run_pipeline(
    *,
    dry_run: bool,
    api_key: str,
    sender: str,
    recipients: list[str],
    redact_recipients: bool,
    call_a_model: str,
    call_b_model: str,
    limit_per_cat: int | None,
    renderer: str = "eml",
) -> None:
    """Execute the full morning_brief pipeline.

    ``renderer`` selects the output path:
        "eml"  — existing renderer.py (unchanged); default.
        "site" — new static-site generator (plan v2 §C, PR-2).
    """
    from morning_brief import collector, selector, summarizer
    from morning_brief.db import bootstrap, insert_run, update_run_completed
    from morning_brief.renderer import render_and_write

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    run_id = _generate_run_id(now)

    conn = bootstrap(_DB_PATH)
    try:
        insert_run(conn, run_id, now)

        stage_durations: dict[str, float] = {}
        run_notes: list[str] = []

        # ---- Collect ----
        t0 = time.time()
        articles, collect_errors = collector.collect(conn, now, dry_run=dry_run)
        stage_durations["collect"] = time.time() - t0
        run_notes.extend(collect_errors)

        # AC12: abort early if fewer than 3 distinct feeds contributed articles
        if not dry_run:
            distinct_sources = len({a.source_name for a in articles})
            if distinct_sources < 3:
                print(
                    f"Insufficient feeds: only {distinct_sources} feed(s) returned articles"
                    " (threshold 3)",
                    file=sys.stderr,
                )
                if collect_errors:
                    print("Feed errors:", file=sys.stderr)
                    for err in collect_errors:
                        print(f"  - {err}", file=sys.stderr)
                sys.exit(2)

        # ---- Select ----
        t0 = time.time()
        articles_by_id = {a.id: a for a in articles}

        if limit_per_cat is not None:
            from morning_brief.selector import precluster, score_candidates, pick_top
            candidates = precluster(articles, dry_run=dry_run)
            scored = score_candidates(conn, candidates, articles_by_id, now)
            scored_candidates = pick_top(scored, max_per_cat=limit_per_cat)
        else:
            scored_candidates = selector.select(conn, articles, now, dry_run=dry_run)

        stage_durations["select"] = time.time() - t0

        # ---- Summarize (Call A + B) ----
        t_summ_start = time.time()

        # Add timing tracking via mutable dict passed by reference
        stage_timings: dict[str, float] = {}

        briefing, key_issues_all, summ_notes, llm_usage = summarizer.run_summarizer(
            conn=conn,
            scored_candidates=scored_candidates,
            articles_by_id=articles_by_id,
            today=now,
            run_id=run_id,
            dry_run=dry_run,
            api_key=api_key,
            call_a_model=call_a_model,
            call_b_model=call_b_model,
            stage_timings=stage_timings,
        )
        run_notes.extend(summ_notes)

        # Use internal timings if available, else split total 25/75
        if "call_a" in stage_timings and "call_b" in stage_timings:
            stage_durations["call_a"] = stage_timings["call_a"]
            stage_durations["call_b"] = stage_timings["call_b"]
        else:
            total_summ = time.time() - t_summ_start
            stage_durations["call_a"] = total_summ * 0.25
            stage_durations["call_b"] = total_summ * 0.75

        # ---- Render ----
        t0 = time.time()
        # Build cluster_id → KeyIssue lookup
        ki_by_id = {ki.cluster_id: ki for ki in key_issues_all}

        output_dir = _DEFAULT_OUTPUT_DIR
        render_output: Path
        if renderer == "site":
            # PR-2 path. SCTEEP tagging lands in a separate Sonnet pass
            # (macro_tagger); when no key is available the tagger is a
            # no-op, so the dry-run flow stays fully offline.
            from morning_brief.site.site_generator import generate_site
            from morning_brief.macro_tagger import tag_macro_clusters

            # macro_tagger works on Cluster objects; the summarizer does not
            # return them directly, so we harvest the MacroTab cluster ids
            # from key_issues and pass a placeholder that the tagger can
            # enrich when/if real clusters are wired in here. Dry-run stays
            # offline because tag_macro_clusters no-ops without a key.
            _ = tag_macro_clusters  # kept in scope for future wiring (PR-3)

            render_output = generate_site(
                briefing=briefing,
                output_dir=output_dir,
                today=now.date(),
                key_issues_by_cluster_id=ki_by_id,
            )
        else:
            render_output, subject = render_and_write(
                briefing=briefing,
                key_issues_by_cluster_id=ki_by_id,
                today=now.date(),
                sender=sender,
                recipients=recipients,
                output_dir=output_dir,
                redact_recipients=redact_recipients,
            )
        stage_durations["render"] = time.time() - t0

        # ---- Persist run completion ----
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        update_run_completed(
            conn=conn,
            run_id=run_id,
            completed_at=completed_at,
            stage_durations=stage_durations,
            llm_usage=llm_usage,
            notes=" | ".join(run_notes),
        )

        print(str(render_output.absolute()))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    _load_env()
    api_key = _require_env("ANTHROPIC_API_KEY")
    sender = _require_env("BRIEF_SENDER")
    recipients_raw = _require_env("BRIEF_RECIPIENTS")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    redact = _env_truthy("REDACT_RECIPIENTS")
    call_a = os.environ.get("LLM_CALL_A_MODEL", _DEFAULT_CALL_A_MODEL)
    call_b = os.environ.get("LLM_CALL_B_MODEL", _DEFAULT_CALL_B_MODEL)
    limit_per_cat: int | None = getattr(args, "limit_per_cat", None)
    renderer: str = getattr(args, "renderer", "site") or "site"

    _run_pipeline(
        dry_run=False,
        api_key=api_key,
        sender=sender,
        recipients=recipients,
        redact_recipients=redact,
        call_a_model=call_a,
        call_b_model=call_b,
        limit_per_cat=limit_per_cat,
        renderer=renderer,
    )


# ---------------------------------------------------------------------------
# Subcommand: dry-run
# ---------------------------------------------------------------------------


def cmd_dry_run(args: argparse.Namespace) -> None:
    _load_env()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "dry-run-key")
    sender = os.environ.get("BRIEF_SENDER", "Morning Brief <brief@example.com>")
    recipients_raw = os.environ.get("BRIEF_RECIPIENTS", "team@example.com")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    redact = _env_truthy("REDACT_RECIPIENTS")
    call_a = os.environ.get("LLM_CALL_A_MODEL", _DEFAULT_CALL_A_MODEL)
    call_b = os.environ.get("LLM_CALL_B_MODEL", _DEFAULT_CALL_B_MODEL)
    limit_per_cat: int | None = getattr(args, "limit_per_cat", None)
    renderer: str = getattr(args, "renderer", "site") or "site"

    _run_pipeline(
        dry_run=True,
        api_key=api_key,
        sender=sender,
        recipients=recipients,
        redact_recipients=redact,
        call_a_model=call_a,
        call_b_model=call_b,
        limit_per_cat=limit_per_cat,
        renderer=renderer,
    )


# ---------------------------------------------------------------------------
# Subcommand: rerender
# ---------------------------------------------------------------------------


def cmd_rerender(args: argparse.Namespace) -> None:
    _load_env()
    run_id: str = args.run_id

    # M1: validate run_id format + path-containment to prevent traversal
    if not _RUN_ID_RE.fullmatch(run_id):
        print(
            f"ERROR: invalid run_id format (expected YYYY-MM-DD-HHMMSS): {run_id!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    run_dir = (_RUN_STATE_DIR / run_id).resolve()
    base = _RUN_STATE_DIR.resolve()
    if base != run_dir and base not in run_dir.parents:
        print("ERROR: run_id escapes run state dir", file=sys.stderr)
        sys.exit(1)

    call_b_path = run_dir / "call_b_response.json"
    ki_path = run_dir / "key_issues.json"

    if not call_b_path.exists():
        print(f"ERROR: {call_b_path} not found", file=sys.stderr)
        sys.exit(1)
    if not ki_path.exists():
        print(f"ERROR: {ki_path} not found", file=sys.stderr)
        sys.exit(1)

    from morning_brief.models import KeyIssue, LLMBriefing
    from morning_brief.renderer import render_and_write

    briefing = LLMBriefing.model_validate(
        json.loads(call_b_path.read_text(encoding="utf-8"))
    )
    ki_data = json.loads(ki_path.read_text(encoding="utf-8"))
    # key_issues.json stores {"key_issues": [...], "misc": [...]}
    all_ki_raw = ki_data.get("key_issues", []) + ki_data.get("misc", [])
    key_issues_all = [KeyIssue.model_validate(ki) for ki in all_ki_raw]
    ki_by_id = {ki.cluster_id: ki for ki in key_issues_all}

    sender = os.environ.get("BRIEF_SENDER", "Morning Brief <brief@example.com>")
    recipients_raw = os.environ.get("BRIEF_RECIPIENTS", "team@example.com")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    redact = _env_truthy("REDACT_RECIPIENTS")

    # Parse date from run_id (YYYY-MM-DD-HHMM)
    try:
        from datetime import date
        today = date.fromisoformat(run_id[:10])
    except ValueError:
        from datetime import date
        today = date.today()

    output_dir = _DEFAULT_OUTPUT_DIR
    eml_path, subject = render_and_write(
        briefing=briefing,
        key_issues_by_cluster_id=ki_by_id,
        today=today,
        sender=sender,
        recipients=recipients,
        output_dir=output_dir,
        redact_recipients=redact,
    )

    print(str(eml_path.absolute()))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="morning_brief",
        description="Sobi-jae trend briefing generator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = sub.add_parser("run", help="Full pipeline with real API calls")
    run_p.add_argument("--limit-per-cat", type=int, dest="limit_per_cat", default=None)
    run_p.add_argument(
        "--renderer",
        choices=("site", "eml"),
        default="site",
        help="Output renderer (default: site). 'site' writes the static "
             "HTML site; 'eml' writes the legacy email file (kept for "
             "fallback during the PR-4 deprecation window).",
    )
    run_p.set_defaults(func=cmd_run)

    # dry-run
    dry_p = sub.add_parser("dry-run", help="Dry-run pipeline on fixture data")
    dry_p.add_argument("--limit-per-cat", type=int, dest="limit_per_cat", default=None)
    dry_p.add_argument(
        "--renderer",
        choices=("site", "eml"),
        default="site",
        help="Output renderer (default: site). 'site' writes the static "
             "HTML site; 'eml' writes the legacy email file (kept for "
             "fallback during the PR-4 deprecation window).",
    )
    dry_p.set_defaults(func=cmd_dry_run)

    # rerender
    rr_p = sub.add_parser("rerender", help="Re-render from persisted run artifacts")
    rr_p.add_argument("run_id", help="Run ID (YYYY-MM-DD-HHMM)")
    rr_p.set_defaults(func=cmd_rerender)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
