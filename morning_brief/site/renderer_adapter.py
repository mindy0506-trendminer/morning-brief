"""Adapter: LLMBriefing + KeyIssue metadata -> Jinja2 template context.

Converts the strict Pydantic briefing produced by Call B into the loose
dict-of-dicts shape the Jinja templates want (cards grouped by tab,
country flags, SCTEEP chips, etc.).

PR-2 scope: pure function, no I/O. All file writes live in
``site_generator.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from morning_brief.models import (
    BriefingItem,
    Category,
    KeyIssue,
    LLMBriefing,
    SceepDimension,
)


# Canonical tab order — MacroTrends first per spec §"Acceptance Criteria"
# ("매크로 트렌드 먼저"). The UI label follows the industry-standard phrasing
# used by WGSN / Mintel ("Macro Trends"); the internal model enum remains
# ``MacroTrends`` and the Korean display is "매크로 트렌드" to avoid the
# 거시+매크로 redundancy that PR-2 browser QA flagged.
TAB_ORDER: tuple[Category, ...] = (
    "MacroTrends",
    "식음료",
    "뷰티",
    "패션",
    "라이프스타일",
    "소비트렌드",
)


# Display names for the tab nav (Korean label + English id for CSS anchors).
TAB_DISPLAY: dict[str, dict[str, str]] = {
    "MacroTrends": {"ko": "매크로 트렌드", "slug": "macro"},
    "식음료": {"ko": "식음료", "slug": "fnb"},
    "뷰티": {"ko": "뷰티", "slug": "beauty"},
    "패션": {"ko": "패션", "slug": "fashion"},
    "라이프스타일": {"ko": "라이프스타일", "slug": "lifestyle"},
    "소비트렌드": {"ko": "소비트렌드", "slug": "consumer"},
}


# Language -> (flag emoji, ISO-3166 alpha-3 for the dominant source country).
# Fallback only — the per-feed ``country`` field in ``config/sources.yml``
# takes precedence via ``Article.source_country`` (plan v2 PR-3 Task 3).
_LANG_COUNTRY: dict[str, tuple[str, str]] = {
    "ko": ("🇰🇷", "KOR"),
    "en": ("🇺🇸", "USA"),
    "ja": ("🇯🇵", "JPN"),
    "zh": ("🇨🇳", "CHN"),
    "es": ("🇪🇸", "ESP"),
}


# ISO-3166 alpha-3 → flag emoji. Covers the publisher geographies the
# 5-language feed set currently touches plus the common neighbours editors
# expect to see on the site. Unknown codes render the generic 🌐 fallback.
_COUNTRY_TO_FLAG: dict[str, str] = {
    "KOR": "🇰🇷",
    "USA": "🇺🇸",
    "GBR": "🇬🇧",
    "JPN": "🇯🇵",
    "CHN": "🇨🇳",
    "ESP": "🇪🇸",
    "FRA": "🇫🇷",
    "DEU": "🇩🇪",
    "ITA": "🇮🇹",
    "CAN": "🇨🇦",
    "AUS": "🇦🇺",
    "SGP": "🇸🇬",
    "THA": "🇹🇭",
    "HKG": "🇭🇰",
    "TWN": "🇹🇼",
    "IND": "🇮🇳",
    "BRA": "🇧🇷",
    "MEX": "🇲🇽",
    "NLD": "🇳🇱",
}

_DEFAULT_FLAG = "🌐"
_DEFAULT_COUNTRY = "INT"


@dataclass
class NewsCardView:
    """Flat view object the template consumes for a single card."""

    card_id: str
    headline_ko: str
    summary_ko: str
    original_headline: str
    source_name: str
    source_url: str
    country_flag: str
    country_code: str  # ISO-3166 alpha-3
    language: str
    sceep_dimensions: list[str] = field(default_factory=list)
    is_paywalled: bool = False


@dataclass
class TabView:
    """One tab: label + list of cards."""

    key: Category
    ko_label: str
    slug: str
    cards: list[NewsCardView]


def _country_for_article(language: str, source_country: str | None) -> tuple[str, str]:
    """Resolve a card's (flag_emoji, ISO-3166 alpha-3) indicator.

    Lookup priority (plan v2 PR-3 Task 3):
      1. ``Article.source_country`` when set (from ``config/sources.yml``).
      2. Language-based default via ``_LANG_COUNTRY``.
      3. ``INT 🌐`` fallback for unknown / missing values.
    """
    if source_country:
        code = source_country.upper()
        flag = _COUNTRY_TO_FLAG.get(code, _DEFAULT_FLAG)
        return (flag, code)
    if language in _LANG_COUNTRY:
        return _LANG_COUNTRY[language]
    return (_DEFAULT_FLAG, _DEFAULT_COUNTRY)


def _pick_primary_article(
    ki: KeyIssue | None,
) -> tuple[str, str, str, str, str | None]:
    """Return (source_name, source_url, original_headline, language, source_country).

    Falls back to placeholder strings when no KeyIssue is available (so the
    template still renders without raising StrictUndefined errors).
    """
    if ki is None or not ki.article_bundle:
        return ("", "", "", "ko", None)
    primary = ki.article_bundle[0]
    return (
        primary.source_name,
        primary.canonical_url or primary.url,
        primary.title,
        primary.language,
        primary.source_country,
    )


def _build_card(
    bi: BriefingItem,
    ki: KeyIssue | None,
    sceep: list[SceepDimension] | None,
) -> NewsCardView:
    (
        source_name,
        source_url,
        original_headline,
        language,
        source_country,
    ) = _pick_primary_article(ki)
    flag, iso3 = _country_for_article(language, source_country)
    return NewsCardView(
        card_id=bi.cluster_id,
        headline_ko=bi.title_ko,
        summary_ko=bi.summary_ko,
        original_headline=original_headline,
        source_name=source_name,
        source_url=source_url,
        country_flag=flag,
        country_code=iso3,
        language=language,
        sceep_dimensions=list(sceep or []),
        is_paywalled=bi.is_paywalled,
    )


def build_template_context(
    briefing: LLMBriefing,
    key_issues_by_cluster_id: dict[str, KeyIssue],
    today_iso: str,
    *,
    sidebar_tree: dict[str, dict[str, list[str]]] | None = None,
    partial_banner_reason: str | None = None,
    sceep_by_cluster: dict[str, list[SceepDimension]] | None = None,
) -> dict[str, Any]:
    """Build the Jinja2 context consumed by ``base.html`` + ``index.html``.

    Parameters
    ----------
    briefing:
        The Call B output. Contains one section per canonical Category.
    key_issues_by_cluster_id:
        Lookup for source metadata + scores.
    today_iso:
        ``YYYY-MM-DD`` string (used for the page header).
    sidebar_tree:
        ``{year: {month: [days]}}`` produced by the site_generator after it
        walks the archive directory. When ``None`` the sidebar renders empty.
    partial_banner_reason:
        If set, the exit-code-6 banner is rendered at the top of the page.
    sceep_by_cluster:
        Mapping produced by ``macro_tagger`` — cluster_id → SCTEEP dims.
        Falls back to ``cluster.sceep_dimensions`` via KeyIssue's cluster
        reference if absent. Only applied to cards in the MacroTrends tab.
    """
    sceep_map = dict(sceep_by_cluster or {})

    tabs: list[TabView] = []
    for cat in TAB_ORDER:
        items = briefing.sections.get(cat, []) or []
        cards: list[NewsCardView] = []
        for bi in items:
            ki = key_issues_by_cluster_id.get(bi.cluster_id)
            sceep: list[SceepDimension] | None = None
            if cat == "MacroTrends":
                # Priority 1: explicit override map (PR-2 test contract).
                # Priority 2: KeyIssue.sceep_dimensions populated by the
                # summarizer → macro_tagger bridge (PR-3 Task 1).
                override = sceep_map.get(bi.cluster_id)
                if override:
                    sceep = override
                elif ki is not None and ki.sceep_dimensions:
                    sceep = list(ki.sceep_dimensions)
                else:
                    sceep = []
            cards.append(_build_card(bi, ki, sceep))
        tabs.append(
            TabView(
                key=cat,
                ko_label=TAB_DISPLAY[cat]["ko"],
                slug=TAB_DISPLAY[cat]["slug"],
                cards=cards,
            )
        )

    return {
        "today": today_iso,
        "tabs": tabs,
        "exec_summary": list(briefing.exec_summary_ko),
        "insight_box": briefing.insight_box_ko,
        "sidebar_tree": sidebar_tree or {},
        "partial_banner_reason": partial_banner_reason,
        "tab_order": [TAB_DISPLAY[c]["slug"] for c in TAB_ORDER],
    }
