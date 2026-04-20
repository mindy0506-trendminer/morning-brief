"""Tests for morning_brief/renderer.py — subject line, HTML rendering, EML structure."""

from __future__ import annotations

import email
import email.header
from datetime import date, datetime

import pytest

from morning_brief.models import Article, BriefingItem, KeyIssue, LLMBriefing
from morning_brief.renderer import (
    build_eml,
    build_render_context,
    build_subject,
    render_html,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_TODAY = date(2026, 4, 18)
_SENDER = "Brief <brief@example.com>"
_RECIPIENTS = ["a@example.com", "b@example.com"]


def _make_article(
    article_id: str = "art_001",
    url: str = "https://example.com/article",
    category: str = "패션",
) -> Article:
    return Article(
        id=article_id,
        title="Test article",
        source_name="TestSource",
        source_type="TraditionalMedia",
        url=url,
        canonical_url=url,
        language="ko",
        published_at=datetime(2026, 4, 18, 4, 0),
        category=category,
        raw_summary="요약 텍스트",
        enriched_text=None,
        fetched_at=datetime(2026, 4, 18, 6, 0),
        extracted_entities=[],
    )


def _make_key_issue(
    cluster_id: str = "cluster_0001",
    category: str = "패션",
    novelty: float = 0.82,
    diffusion: float = 0.71,
    combined: float = 0.74,
    article_url: str = "https://example.com/article",
) -> KeyIssue:
    return KeyIssue(
        cluster_id=cluster_id,
        category=category,
        canonical_entity_ko="자라 AI 캠페인",
        primary_entity="Zara",
        novelty_score=novelty,
        diffusion_score=diffusion,
        combined_score=combined,
        article_bundle=[_make_article(url=article_url)],
    )


def _make_briefing_item(
    cluster_id: str = "cluster_0001",
    title_ko: str = "자라 생성형 캠페인 전면화",
    summary_ko: str = "자라가 생성형 이미지로 캠페인 전체를 대체했다.",
    is_paywalled: bool = False,
) -> BriefingItem:
    return BriefingItem(
        cluster_id=cluster_id,
        title_ko=title_ko,
        summary_ko=summary_ko,
        is_paywalled=is_paywalled,
    )


def _make_briefing(
    sections: dict | None = None,
    misc: list | None = None,
) -> LLMBriefing:
    if sections is None:
        sections = {
            "패션": [_make_briefing_item()],
        }
    return LLMBriefing(
        schema_version="v2",
        exec_summary_ko=[
            "패션: Zara AI 캠페인 확산",
            "뷰티: 숏폼 리뷰 채널 부상",
            "라이프스타일: 자율 제어 가전 경쟁",
        ],
        sections=sections,
        misc_observations_ko=misc,
        insight_box_ko="인사이트 박스 텍스트입니다.",
    )


# ---------------------------------------------------------------------------
# 1. build_subject — all 5 categories, no misc
# ---------------------------------------------------------------------------

def test_build_subject_all_5_categories_no_misc():
    # Post-D10-A: Hospitality collapsed into 라이프스타일, so the 5 legacy
    # inputs become 4 distinct canonical slots. 소비트렌드 replaces the fifth
    # seat so the "all industry tabs present" surface is still exercised.
    result = build_subject(
        sections_keys=["F&B", "뷰티", "패션", "라이프스타일", "소비트렌드"],
        misc_nonempty=False,
        today=_TODAY,
    )
    assert (
        result
        == "[소비재 트렌드 조간] 2026-04-18 (F&B/뷰티/패션/라이프스타일/소비트렌드)"
    )


# ---------------------------------------------------------------------------
# 2. build_subject — partial + misc
# ---------------------------------------------------------------------------

def test_build_subject_partial_with_misc():
    result = build_subject(
        sections_keys=["F&B", "뷰티", "라이프스타일"],
        misc_nonempty=True,
        today=_TODAY,
    )
    assert result == "[소비재 트렌드 조간] 2026-04-18 (F&B/뷰티/라이프스타일 · 기타 관찰)"


# ---------------------------------------------------------------------------
# 3. build_subject — empty sections, misc only
# ---------------------------------------------------------------------------

def test_build_subject_empty_sections_misc_only():
    result = build_subject(
        sections_keys=[],
        misc_nonempty=True,
        today=_TODAY,
    )
    assert result == "[소비재 트렌드 조간] 2026-04-18 (기타 관찰)"


# ---------------------------------------------------------------------------
# 4. Blocker-3: 1-cluster category renders as section, NOT pushed to misc
# ---------------------------------------------------------------------------

def test_render_one_cluster_category():
    """F&B section with exactly 1 item must render as a <section> with that item."""
    briefing = _make_briefing(
        sections={
            "F&B": [
                BriefingItem(
                    cluster_id="cl_food_001",
                    title_ko="발효 음료 트렌드",
                    summary_ko="국내 기능성 발효 음료 시장이 급성장 중이다.",
                    is_paywalled=False,
                )
            ]
        }
    )
    ki_map = {
        "cl_food_001": _make_key_issue(
            cluster_id="cl_food_001",
            category="F&B",
            article_url="https://example.com/food",
        )
    }
    context = build_render_context(briefing, ki_map, _TODAY, _SENDER, _RECIPIENTS, False)
    html = render_html(context)

    # Should have F&B section. Jinja autoescapes '&' → '&amp;' in HTML output.
    assert "F&amp;B" in html
    assert "발효 음료 트렌드" in html
    # Should NOT appear in misc section
    # The misc section header is "기타 관찰"
    # Item appears under F&B — misc block should not contain it
    # (misc is empty in this briefing)
    assert context["misc"] == []


# ---------------------------------------------------------------------------
# 5. Empty category omitted from HTML
# ---------------------------------------------------------------------------

def test_render_empty_category_omitted():
    """패션 missing from sections dict → no 패션 section heading in HTML."""
    # Build a briefing manually so the exec_summary lines do not mention the
    # category tokens we later assert are absent. This keeps the assertion
    # focused on the section-heading-rendering invariant.
    briefing = LLMBriefing(
        schema_version="v2",
        exec_summary_ko=[
            "요약 1",
            "요약 2",
            "요약 3",
        ],
        sections={
            "F&B": [
                BriefingItem(
                    cluster_id="cl_food_001",
                    title_ko="식품 트렌드",
                    summary_ko="국내 식품 트렌드 요약.",
                    is_paywalled=False,
                )
            ]
        },
        misc_observations_ko=None,
        insight_box_ko="인사이트 박스 텍스트입니다.",
    )
    ki_map = {
        "cl_food_001": _make_key_issue(cluster_id="cl_food_001", category="F&B")
    }
    context = build_render_context(briefing, ki_map, _TODAY, _SENDER, _RECIPIENTS, False)
    html = render_html(context)

    # 패션 section heading should not appear (nothing else in the briefing
    # contains the Korean token, so its absence is proof the template did
    # not emit the empty Fashion section).
    assert "패션" not in html
    # F&B section should appear (autoescaped).
    assert "F&amp;B" in html
    # The context sections should not contain 패션.
    assert "패션" not in context["sections"]


# ---------------------------------------------------------------------------
# 6. Score pills come from Python KeyIssue, not LLM BriefingItem
# ---------------------------------------------------------------------------

def test_score_pills_come_from_python_not_llm():
    """combined_score=0.74 from KeyIssue must appear in rendered HTML."""
    briefing = _make_briefing(
        sections={
            "패션": [_make_briefing_item(cluster_id="cl_sc_001")]
        }
    )
    ki_map = {
        "cl_sc_001": _make_key_issue(
            cluster_id="cl_sc_001",
            novelty=0.82,
            diffusion=0.71,
            combined=0.74,
        )
    }
    context = build_render_context(briefing, ki_map, _TODAY, _SENDER, _RECIPIENTS, False)
    html = render_html(context)

    assert "0.74" in html  # combined score
    assert "0.82" in html  # novelty
    assert "0.71" in html  # diffusion


# ---------------------------------------------------------------------------
# 7. EML structure — multipart with text + HTML
# ---------------------------------------------------------------------------

def test_eml_structure():
    briefing = _make_briefing()
    ki_map = {"cluster_0001": _make_key_issue()}
    context = build_render_context(briefing, ki_map, _TODAY, _SENDER, _RECIPIENTS, False)
    html = render_html(context)
    subject = "[소비재 트렌드 조간] 2026-04-18 (Fashion)"
    eml_bytes = build_eml(
        html=html,
        plain_text="plain text version",
        subject=subject,
        sender=_SENDER,
        recipients=_RECIPIENTS,
        redact_recipients=False,
    )

    msg = email.message_from_bytes(eml_bytes)
    # Decode RFC 2047 encoded subject (non-ASCII chars get base64/QP encoded)
    decoded_subject = email.header.decode_header(msg["Subject"])
    subject_str = "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in decoded_subject
    )
    assert subject_str == subject
    assert msg["From"] == _SENDER
    assert "a@example.com" in msg["To"]

    # Must be multipart
    assert msg.is_multipart()
    content_types = {part.get_content_type() for part in msg.walk()}
    assert "text/plain" in content_types
    assert "text/html" in content_types


# ---------------------------------------------------------------------------
# 8. EML redact recipients
# ---------------------------------------------------------------------------

def test_eml_redact_recipients():
    briefing = _make_briefing()
    ki_map = {"cluster_0001": _make_key_issue()}
    context = build_render_context(briefing, ki_map, _TODAY, _SENDER, _RECIPIENTS, True)
    html = render_html(context)
    eml_bytes = build_eml(
        html=html,
        plain_text="plain",
        subject="subject",
        sender=_SENDER,
        recipients=_RECIPIENTS,
        redact_recipients=True,
    )

    msg = email.message_from_bytes(eml_bytes)
    assert msg["To"] == "__REDACTED__"
    # Real addresses must not appear in To header
    assert "a@example.com" not in (msg["To"] or "")


# ---------------------------------------------------------------------------
# 9. No external stylesheet in rendered HTML
# ---------------------------------------------------------------------------

def test_html_no_external_stylesheet():
    briefing = _make_briefing()
    ki_map = {"cluster_0001": _make_key_issue()}
    context = build_render_context(briefing, ki_map, _TODAY, _SENDER, _RECIPIENTS, False)
    html = render_html(context)

    assert '<link rel="stylesheet"' not in html
    assert 'src="http' not in html
