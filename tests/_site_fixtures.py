"""Shared fixture helpers for PR-2 site / macro_tagger tests.

Keeps test setup in one place so the six test modules stay focused on
assertions rather than scaffolding.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from morning_brief.models import (
    Article,
    BriefingItem,
    KeyIssue,
    LLMBriefing,
)


_LANG_BY_TAB: dict[str, str] = {
    "MacroTrends": "en",
    "식음료": "ko",
    "뷰티": "en",
    "패션": "ja",
    "라이프스타일": "zh",
    "소비트렌드": "es",
}


# Per-tab hostname used to build distinct per-article URLs. Each article
# under these tabs gets a full article-level path (``/article/{slug}-{i}``)
# so the source link never collapses to a bare homepage URL (Issue A).
_HOST_BY_TAB: dict[str, str] = {
    "MacroTrends": "reuters.com",
    "식음료": "thinkfood.co.kr",
    "뷰티": "beautymatter.com",
    "패션": "wwd.com",
    "라이프스타일": "dezeen.com",
    "소비트렌드": "adage.com",
}


def make_article(
    *,
    article_id: str,
    language: str = "ko",
    source_name: str = "TestSource",
    title: str = "Test original headline",
    url: str = "https://example.com/article",
    source_country: str | None = None,
) -> Article:
    return Article(
        id=article_id,
        title=title,
        source_name=source_name,
        source_type="TraditionalMedia",
        url=url,
        canonical_url=url,
        language=language,
        published_at=datetime(2026, 4, 18, 4, 0),
        category="패션",
        raw_summary="raw",
        enriched_text=None,
        fetched_at=datetime(2026, 4, 18, 6, 0),
        extracted_entities=[],
        source_country=source_country,
    )


def make_key_issue(
    *,
    cluster_id: str,
    article: Article,
    category: str,
) -> KeyIssue:
    return KeyIssue(
        cluster_id=cluster_id,
        category=category,
        canonical_entity_ko="테스트 엔티티",
        primary_entity="TestEntity",
        novelty_score=0.5,
        diffusion_score=0.6,
        combined_score=0.55,
        article_bundle=[article],
    )


def make_full_briefing(
    *,
    cards_per_tab: int = 15,
) -> tuple[LLMBriefing, dict[str, KeyIssue]]:
    """Build an LLMBriefing that covers all 6 tabs with ``cards_per_tab`` cards.

    Returns (briefing, key_issues_by_cluster_id). The KeyIssue map carries
    distinct source_name / original_headline per card so renderer tests can
    assert specific strings.
    """
    tabs = ["MacroTrends", "식음료", "뷰티", "패션", "라이프스타일", "소비트렌드"]
    sections: dict[str, list[BriefingItem]] = {}
    ki_by_id: dict[str, KeyIssue] = {}

    for tab in tabs:
        items: list[BriefingItem] = []
        for i in range(cards_per_tab):
            cid = f"{tab}_c{i:02d}"
            lang = _LANG_BY_TAB[tab]
            source_name = f"{tab}Source{i}"
            original = f"Original {tab} headline #{i}"
            # Distinct per-article URL with an explicit ``/article/`` path
            # segment so footer source links never collapse to a homepage.
            host = _HOST_BY_TAB[tab]
            url = f"https://{host}/article/{tab.lower()}-{i:02d}"
            # Most cards rely on language-default flags (so PR-2's
            # test_country_indicator_present keeps passing). A handful of
            # cards opt into an explicit ``source_country`` override so
            # PR-3's flag-diversity regression coverage exercises the
            # ``source_country > language fallback`` path.
            override: str | None = None
            if tab == "MacroTrends" and i == 1:
                override = "GBR"  # English source from the UK
            elif tab == "뷰티" and i == 2:
                override = "CAN"  # English source from Canada
            article = make_article(
                article_id=f"{tab}_a{i:02d}",
                language=lang,
                source_name=source_name,
                title=original,
                url=url,
                source_country=override,
            )
            items.append(
                BriefingItem(
                    cluster_id=cid,
                    title_ko=f"{tab} 한국어 헤드라인 {i}",
                    summary_ko=f"{tab}의 오늘 요약 {i}번: 세 줄 이내로 내용을 담는다.",
                    is_paywalled=(i == 0),
                )
            )
            ki_by_id[cid] = make_key_issue(cluster_id=cid, article=article, category=tab)
        sections[tab] = items

    briefing = LLMBriefing(
        schema_version="v2",
        exec_summary_ko=[
            "패션: 테스트 한줄 1",
            "뷰티: 테스트 한줄 2",
            "라이프스타일: 테스트 한줄 3",
        ],
        sections=sections,
        misc_observations_ko=None,
        insight_box_ko="테스트 인사이트 박스 문장입니다.",
    )
    return briefing, ki_by_id


def make_sceep_map(briefing: LLMBriefing) -> dict[str, Any]:
    """Return a sceep mapping keyed by macro cluster_id with 1-3 dims each."""
    out: dict[str, list[str]] = {}
    macro_items = briefing.sections.get("MacroTrends", []) or []
    assigned = [
        ["Economy", "Politics"],
        ["Technology"],
        ["Social", "Culture"],
        ["Environment"],
        ["Economy"],
    ]
    for idx, bi in enumerate(macro_items):
        out[bi.cluster_id] = assigned[idx % len(assigned)]
    return out
