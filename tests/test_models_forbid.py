"""Acceptance tests for strict LLM response models (extra='forbid')."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from morning_brief.models import (
    Article,
    BriefingItem,
    CallAClusterOut,
    CallAResponse,
    CompanyTag,
    LLMBriefing,
)


# -------- Helpers: minimal valid payloads --------

_VALID_CLUSTER_OUT = dict(
    input_cluster_ids=["c1"],
    category_confirmed="F&B",
    canonical_entity_ko="풀무원",
    is_cross_lingual_merge=False,
    key_entities=["Pulmuone"],
)

_VALID_CALL_A_RESPONSE = dict(
    clusters=[_VALID_CLUSTER_OUT],
)

_VALID_BRIEFING_ITEM = dict(
    cluster_id="c1",
    title_ko="풀무원 신제품 출시",
    summary_ko="풀무원이 신제품을 출시했다.",
    is_paywalled=False,
)

_VALID_LLM_BRIEFING = dict(
    schema_version="v2",
    exec_summary_ko=["요약 1", "요약 2", "요약 3"],
    sections={"F&B": [_VALID_BRIEFING_ITEM]},
    misc_observations_ko=None,
    insight_box_ko="이번 주 주목할 트렌드.",
)


# -------- extra="forbid" tests --------


class TestCallAClusterOutForbidsExtra:
    def test_rejects_extra_field(self):
        """CallAClusterOut must raise ValidationError when an unknown field is present."""
        with pytest.raises(ValidationError):
            CallAClusterOut(**_VALID_CLUSTER_OUT, novelty_score=0.9)

    def test_accepts_valid_payload(self):
        """CallAClusterOut accepts a minimal valid payload."""
        obj = CallAClusterOut(**_VALID_CLUSTER_OUT)
        assert obj.category_confirmed == "F&B"


class TestCallAResponseForbidsExtra:
    def test_rejects_extra_field(self):
        """CallAResponse must raise ValidationError when an unknown field is present."""
        with pytest.raises(ValidationError):
            CallAResponse(**_VALID_CALL_A_RESPONSE, novelty_score=0.9)

    def test_accepts_valid_payload(self):
        """CallAResponse accepts a minimal valid payload."""
        obj = CallAResponse(**_VALID_CALL_A_RESPONSE)
        assert len(obj.clusters) == 1


class TestBriefingItemForbidsExtra:
    def test_rejects_extra_field(self):
        """BriefingItem must raise ValidationError when an unknown field is present."""
        with pytest.raises(ValidationError):
            BriefingItem(**_VALID_BRIEFING_ITEM, novelty_score=0.9)

    def test_accepts_valid_payload(self):
        """BriefingItem accepts a minimal valid payload."""
        obj = BriefingItem(**_VALID_BRIEFING_ITEM)
        assert obj.cluster_id == "c1"


class TestLLMBriefingForbidsExtra:
    def test_rejects_extra_field(self):
        """LLMBriefing must raise ValidationError when an unknown field is present."""
        with pytest.raises(ValidationError):
            LLMBriefing(**_VALID_LLM_BRIEFING, novelty_score=0.9)

    def test_accepts_valid_payload(self):
        """LLMBriefing accepts a minimal valid payload."""
        obj = LLMBriefing(**_VALID_LLM_BRIEFING)
        assert obj.schema_version == "v2"


# -------- exec_summary_ko length validator --------


class TestExecSummaryLength:
    def test_rejects_two_items(self):
        """exec_summary_ko with 2 items must raise ValidationError."""
        payload = {**_VALID_LLM_BRIEFING, "exec_summary_ko": ["요약 1", "요약 2"]}
        with pytest.raises(ValidationError):
            LLMBriefing(**payload)

    def test_rejects_four_items(self):
        """exec_summary_ko with 4 items must raise ValidationError."""
        payload = {**_VALID_LLM_BRIEFING, "exec_summary_ko": ["요약 1", "요약 2", "요약 3", "요약 4"]}
        with pytest.raises(ValidationError):
            LLMBriefing(**payload)

    def test_rejects_empty_list(self):
        """exec_summary_ko with 0 items must raise ValidationError."""
        payload = {**_VALID_LLM_BRIEFING, "exec_summary_ko": []}
        with pytest.raises(ValidationError):
            LLMBriefing(**payload)

    def test_accepts_exactly_three(self):
        """exec_summary_ko with exactly 3 items must be accepted."""
        obj = LLMBriefing(**_VALID_LLM_BRIEFING)
        assert len(obj.exec_summary_ko) == 3


# -------- schema_version literal --------


class TestSchemaVersion:
    def test_rejects_v1(self):
        """schema_version='v1' must raise ValidationError."""
        payload = {**_VALID_LLM_BRIEFING, "schema_version": "v1"}
        with pytest.raises(ValidationError):
            LLMBriefing(**payload)

    def test_rejects_wrong_string(self):
        """schema_version='v3' must raise ValidationError."""
        payload = {**_VALID_LLM_BRIEFING, "schema_version": "v3"}
        with pytest.raises(ValidationError):
            LLMBriefing(**payload)

    def test_accepts_v2(self):
        """schema_version='v2' must be accepted."""
        obj = LLMBriefing(**_VALID_LLM_BRIEFING)
        assert obj.schema_version == "v2"


# -------- Category Literal rename (plan v2 §D10-A) --------


class TestCategoryLiteralRename:
    """Category Literal must accept canonical D10-A values and reject the fully
    retired legacy names. PR-2 QA Issue C: ``식음료`` is the new canonical label
    for food & beverage; ``F&B`` remains accepted for backward compatibility
    (pre-migration briefing.db rows + EML-renderer fixtures)."""

    _CANONICAL = [
        "식음료",
        "F&B",
        "뷰티",
        "패션",
        "라이프스타일",
        "소비트렌드",
        "MacroTrends",
    ]
    _LEGACY = ["Food", "Beauty", "Fashion", "Living", "Hospitality"]

    @pytest.mark.parametrize("cat", _CANONICAL)
    def test_call_a_accepts_canonical(self, cat):
        payload = {**_VALID_CLUSTER_OUT, "category_confirmed": cat}
        obj = CallAClusterOut(**payload)
        assert obj.category_confirmed == cat

    @pytest.mark.parametrize("cat", _LEGACY)
    def test_call_a_rejects_legacy(self, cat):
        payload = {**_VALID_CLUSTER_OUT, "category_confirmed": cat}
        with pytest.raises(ValidationError):
            CallAClusterOut(**payload)

    @pytest.mark.parametrize("cat", _CANONICAL)
    def test_llm_briefing_accepts_canonical_section_key(self, cat):
        payload = {**_VALID_LLM_BRIEFING, "sections": {cat: [_VALID_BRIEFING_ITEM]}}
        obj = LLMBriefing(**payload)
        assert cat in obj.sections

    @pytest.mark.parametrize("cat", _LEGACY)
    def test_llm_briefing_rejects_legacy_section_key(self, cat):
        payload = {**_VALID_LLM_BRIEFING, "sections": {cat: [_VALID_BRIEFING_ITEM]}}
        with pytest.raises(ValidationError):
            LLMBriefing(**payload)


# -------- Widened language Literal (plan v2 §A5a/A5b) --------


_ARTICLE_BASE = dict(
    id="art_x",
    title="Test",
    source_name="Src",
    source_type="TraditionalMedia",
    url="https://example.com/x",
    canonical_url="https://example.com/x",
    published_at=datetime(2026, 4, 18, 6, 0, 0),
    category="F&B",
    raw_summary="summary",
    enriched_text=None,
    fetched_at=datetime(2026, 4, 18, 6, 0, 0),
    extracted_entities=[],
)


class TestArticleLanguageLiteral:
    """Article.language must accept the 5-language set and reject anything else."""

    @pytest.mark.parametrize("lang", ["ko", "en", "ja", "zh", "es"])
    def test_accepts_supported_language(self, lang):
        obj = Article(**_ARTICLE_BASE, language=lang)
        assert obj.language == lang

    @pytest.mark.parametrize("lang", ["de", "fr", "it", "ru", "pt", "vi", ""])
    def test_rejects_unsupported_language(self, lang):
        with pytest.raises(ValidationError):
            Article(**_ARTICLE_BASE, language=lang)


# -------- CompanyTag model (plan v2 §D3 / PR-1 Task 2c) --------


class TestCompanyTag:
    """CompanyTag is strict, uses the 'class' alias, and validates the 3-class set."""

    @pytest.mark.parametrize("company_class", ["대기업", "유통", "혁신스타트업"])
    def test_accepts_canonical_class(self, company_class):
        tag = CompanyTag.model_validate(
            {"name": "Sample", "class": company_class, "confidence": 0.9}
        )
        assert tag.class_ == company_class

    def test_rejects_unknown_class(self):
        with pytest.raises(ValidationError):
            CompanyTag.model_validate(
                {"name": "Sample", "class": "Enterprise", "confidence": 0.9}
            )

    def test_rejects_extra_field(self):
        with pytest.raises(ValidationError):
            CompanyTag.model_validate(
                {
                    "name": "Sample",
                    "class": "대기업",
                    "confidence": 0.9,
                    "unexpected": True,
                }
            )

    def test_round_trips_with_class_alias(self):
        tag = CompanyTag.model_validate(
            {"name": "Coupang", "class": "유통", "confidence": 0.88}
        )
        dumped = tag.model_dump(by_alias=True)
        assert dumped == {"name": "Coupang", "class": "유통", "confidence": 0.88}

    def test_article_defaults_to_empty_company_tags(self):
        obj = Article(**_ARTICLE_BASE, language="ko")
        assert obj.company_tags == []

    def test_article_accepts_company_tags(self):
        tags = [
            CompanyTag(name="CJ제일제당", class_="대기업", confidence=0.95),
        ]
        obj = Article(**_ARTICLE_BASE, language="ko", company_tags=tags)
        assert len(obj.company_tags) == 1
        assert obj.company_tags[0].name == "CJ제일제당"
