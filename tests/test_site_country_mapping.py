"""PR-3 Task 3 — country/flag resolution via ``Article.source_country``.

The previous implementation mapped language → country, which produced a
wall of 🇺🇸 for every English source regardless of the publisher's actual
HQ. The new contract is:

  1. ``Article.source_country`` (from ``config/sources.yml``) wins.
  2. Fall back to the language-based default map.
  3. Unknown codes render the ``INT 🌐`` international default.
"""

from __future__ import annotations

from datetime import datetime

from morning_brief.models import Article, BriefingItem, KeyIssue, LLMBriefing
from morning_brief.site.renderer_adapter import build_template_context


def _article(lang: str, country: str | None) -> Article:
    return Article(
        id="art_x",
        title="headline",
        source_name="Src",
        source_type="TraditionalMedia",
        url="https://example.com/article/x",
        canonical_url="https://example.com/article/x",
        language=lang,  # type: ignore[arg-type]
        published_at=datetime(2026, 4, 18, 4, 0),
        category="패션",
        raw_summary="raw",
        enriched_text=None,
        fetched_at=datetime(2026, 4, 18, 6, 0),
        extracted_entities=[],
        source_country=country,
    )


def _briefing(cid: str = "c1") -> tuple[LLMBriefing, dict[str, KeyIssue]]:
    bi = BriefingItem(
        cluster_id=cid,
        title_ko="헤드라인 한국어",
        summary_ko="요약 한국어 문장입니다.",
        is_paywalled=False,
    )
    briefing = LLMBriefing(
        schema_version="v2",
        exec_summary_ko=["요약 1", "요약 2", "요약 3"],
        sections={"패션": [bi]},
        misc_observations_ko=None,
        insight_box_ko="인사이트 박스 문장입니다.",
    )
    return briefing, {}


def _build_card(article: Article) -> dict:
    briefing, _ = _briefing("c1")
    ki = KeyIssue(
        cluster_id="c1",
        category="패션",
        canonical_entity_ko="엔티티",
        primary_entity="Entity",
        novelty_score=0.5,
        diffusion_score=0.5,
        combined_score=0.5,
        article_bundle=[article],
    )
    ctx = build_template_context(
        briefing=briefing,
        key_issues_by_cluster_id={"c1": ki},
        today_iso="2026-04-18",
    )
    fashion_tab = next(t for t in ctx["tabs"] if t.key == "패션")
    assert len(fashion_tab.cards) == 1
    card = fashion_tab.cards[0]
    return {"flag": card.country_flag, "code": card.country_code}


def test_source_country_overrides_language_default() -> None:
    """en + source_country=GBR renders 🇬🇧 GBR, not 🇺🇸 USA."""
    article = _article(lang="en", country="GBR")
    got = _build_card(article)
    assert got["code"] == "GBR"
    assert got["flag"] == "🇬🇧"


def test_language_fallback_when_country_missing() -> None:
    """No source_country → language-based default map."""
    for lang, expected_code, expected_flag in (
        ("ko", "KOR", "🇰🇷"),
        ("en", "USA", "🇺🇸"),
        ("ja", "JPN", "🇯🇵"),
        ("zh", "CHN", "🇨🇳"),
        ("es", "ESP", "🇪🇸"),
    ):
        article = _article(lang=lang, country=None)
        got = _build_card(article)
        assert got["code"] == expected_code, f"lang={lang} code mismatch"
        assert got["flag"] == expected_flag, f"lang={lang} flag mismatch"


def test_unknown_country_renders_international_default() -> None:
    """Unknown ISO-3 code → INT 🌐."""
    article = _article(lang="en", country="ZZZ")
    got = _build_card(article)
    # Still returns the code the caller supplied so ops can see it in QA…
    assert got["code"] == "ZZZ"
    # …but the flag falls through to the international default emoji.
    assert got["flag"] == "🌐"
