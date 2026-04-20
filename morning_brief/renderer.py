"""Renderer: build Jinja2 HTML briefing, EML file, and subject line."""

from __future__ import annotations

import re
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from morning_brief.models import KeyIssue, LLMBriefing

# Canonical category order (Blocker-3 rule). Renamed in PR-1 per plan v2
# §D10-A: MacroTab/소비트렌드 added, Hospitality collapsed into 라이프스타일.
_CANONICAL_ORDER = [
    "F&B",
    "뷰티",
    "패션",
    "라이프스타일",
    "소비트렌드",
    "MacroTrends",
]

# The canonical keys are already Korean (or the self-explanatory "F&B"/
# "MacroTrends" tokens), so the display map becomes an identity — kept as
# a dict so the Jinja template can stay unchanged.
_CATEGORY_KOREAN_NAMES: dict[str, str] = {cat: cat for cat in _CANONICAL_ORDER}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def build_render_context(
    briefing: LLMBriefing,
    key_issues_by_cluster_id: dict[str, KeyIssue],
    today: date,
    sender: str,
    recipients: list[str],
    redact_recipients: bool,
) -> dict[str, Any]:
    """Build the template context dict from LLMBriefing + KeyIssue scores."""
    sections: dict[str, list[dict[str, Any]]] = {}

    for cat in _CANONICAL_ORDER:
        items = briefing.sections.get(cat)
        if not items:
            continue
        rendered_items: list[dict[str, Any]] = []
        for bi in items:
            ki = key_issues_by_cluster_id.get(bi.cluster_id)
            if ki is not None:
                scores = {
                    "novelty": ki.novelty_score,
                    "diffusion": ki.diffusion_score,
                    "combined": ki.combined_score,
                }
                # Deduplicated source URLs, max 3
                seen: set[str] = set()
                source_urls: list[str] = []
                for article in ki.article_bundle:
                    u = article.canonical_url
                    if u and u not in seen:
                        seen.add(u)
                        source_urls.append(u)
                    if len(source_urls) >= 3:
                        break
            else:
                scores = {"novelty": 0.0, "diffusion": 0.0, "combined": 0.0}
                source_urls = []

            rendered_items.append(
                {
                    "title_ko": bi.title_ko,
                    "summary_ko": bi.summary_ko,
                    "scores": scores,
                    "source_urls": source_urls,
                    "is_paywalled": bi.is_paywalled,
                }
            )
        sections[cat] = rendered_items

    # Misc observations
    misc: list[dict[str, Any]] = []
    if briefing.misc_observations_ko:
        for bi in briefing.misc_observations_ko:
            ki = key_issues_by_cluster_id.get(bi.cluster_id)
            seen = set()
            source_urls = []
            if ki is not None:
                for article in ki.article_bundle:
                    u = article.canonical_url
                    if u and u not in seen:
                        seen.add(u)
                        source_urls.append(u)
                    if len(source_urls) >= 3:
                        break
            misc.append(
                {
                    "title_ko": bi.title_ko,
                    "summary_ko": bi.summary_ko,
                    "source_urls": source_urls,
                }
            )

    recipients_display = (
        "__REDACTED__" if redact_recipients else ", ".join(recipients)
    )

    return {
        "date_str": today.isoformat(),
        "exec_summary": briefing.exec_summary_ko,
        "sections": sections,
        "misc": misc,
        "insight_box": briefing.insight_box_ko,
        "sender": sender,
        "recipients_display": recipients_display,
        "category_korean_names": _CATEGORY_KOREAN_NAMES,
    }


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def render_html(context: dict[str, Any]) -> str:
    """Render the Jinja2 template with the given context."""
    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent)),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template("briefing.html.j2")
    return tmpl.render(**context)


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


def html_to_plain_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace into readable plain text."""
    text = _HTML_TAG_RE.sub(" ", html)
    text = _WS_RE.sub(" ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Subject line
# ---------------------------------------------------------------------------


def build_subject(
    sections_keys: list[str],
    misc_nonempty: bool,
    today: date,
) -> str:
    """Build the email subject per Blocker-3 dynamic rule.

    Canonical order: Food, Beauty, Fashion, Living, Hospitality.
    Only categories present in sections_keys appear (in canonical order).
    Appends '기타 관찰' if misc is non-empty.
    """
    present = [cat for cat in _CANONICAL_ORDER if cat in sections_keys]
    parts_str = "/".join(present) if present else ""

    if parts_str and misc_nonempty:
        inner = f"{parts_str} · 기타 관찰"
    elif parts_str:
        inner = parts_str
    elif misc_nonempty:
        inner = "기타 관찰"
    else:
        inner = ""

    return f"[소비재 트렌드 조간] {today.isoformat()} ({inner})"


# ---------------------------------------------------------------------------
# EML construction
# ---------------------------------------------------------------------------


def build_eml(
    html: str,
    plain_text: str,
    subject: str,
    sender: str,
    recipients: list[str],
    redact_recipients: bool,
) -> bytes:
    """Build a multipart/alternative EML (plain + HTML) as bytes."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "__REDACTED__" if redact_recipients else ", ".join(recipients)
    msg.set_content(plain_text, subtype="plain", charset="utf-8", cte="base64")
    msg.add_alternative(html, subtype="html", charset="utf-8", cte="base64")
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def write_eml(eml_bytes: bytes, output_path: Path) -> Path:
    """Ensure parent dir exists, write EML bytes, return path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(eml_bytes)
    return output_path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def render_and_write(
    briefing: LLMBriefing,
    key_issues_by_cluster_id: dict[str, KeyIssue],
    today: date,
    sender: str,
    recipients: list[str],
    output_dir: Path,
    redact_recipients: bool,
) -> tuple[Path, str]:
    """Full render pipeline: context → HTML → subject → EML → write.

    Returns (eml_path, subject).
    """
    context = build_render_context(
        briefing=briefing,
        key_issues_by_cluster_id=key_issues_by_cluster_id,
        today=today,
        sender=sender,
        recipients=recipients,
        redact_recipients=redact_recipients,
    )

    html = render_html(context)
    plain_text = html_to_plain_text(html)

    sections_keys = list(context["sections"].keys())
    misc_nonempty = bool(context["misc"])
    subject = build_subject(sections_keys, misc_nonempty, today)

    eml_bytes = build_eml(
        html=html,
        plain_text=plain_text,
        subject=subject,
        sender=sender,
        recipients=recipients,
        redact_recipients=redact_recipients,
    )

    eml_path = output_dir / f"briefing_{today.isoformat()}.eml"
    write_eml(eml_bytes, eml_path)

    return eml_path, subject
