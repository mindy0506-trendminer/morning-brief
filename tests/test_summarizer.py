"""Acceptance tests for morning_brief/summarizer.py — Step 5.

All tests mock anthropic.Anthropic.messages.create — zero network calls.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pydantic
import pytest
from anthropic import APIConnectionError

from morning_brief import summarizer as sz
from morning_brief.db import bootstrap, insert_run
from morning_brief.models import (
    Article,
    CallAResponse,
    CandidateCluster,
    Cluster,
    KeyIssue,
    LLMBriefing,
)
from morning_brief.summarizer import (
    LLMClient,
    finalize_sections,
    merge_candidate_clusters,
    run_summarizer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime(2026, 4, 18, 9, 0, 0, tzinfo=timezone.utc)


def _make_article(
    *,
    aid: str | None = None,
    title: str = "Test Article",
    language: str = "ko",
    category: str | None = "패션",
    source_name: str = "Source1",
    source_type: str = "TraditionalMedia",
    published_at: datetime | None = None,
    extracted_entities: list[str] | None = None,
    raw_summary: str = "",
    enriched_text: str | None = None,
) -> Article:
    now = _now()
    return Article(
        id=aid or str(uuid.uuid4()),
        title=title,
        source_name=source_name,
        source_type=source_type,  # type: ignore[arg-type]
        url=f"https://example.com/{uuid.uuid4()}",
        canonical_url=f"https://example.com/{uuid.uuid4()}",
        language=language,  # type: ignore[arg-type]
        published_at=published_at or now,
        category=category,
        raw_summary=raw_summary,
        enriched_text=enriched_text,
        fetched_at=now,
        extracted_entities=extracted_entities or [],
    )


def _make_candidate(
    *,
    cid: str | None = None,
    article_ids: list[str],
    category: str = "패션",
    language: str = "ko",
    rep_title: str = "Rep Title",
) -> CandidateCluster:
    return CandidateCluster(
        id=cid or str(uuid.uuid4()),
        category=category,
        article_ids=article_ids,
        representative_title=rep_title,
        language=language,  # type: ignore[arg-type]
    )


def _mock_response(text: str, usage_kwargs: dict | None = None) -> SimpleNamespace:
    """Construct a minimal mock of anthropic.types.Message."""
    usage_kwargs = usage_kwargs or {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    return SimpleNamespace(
        content=[SimpleNamespace(text=text, type="text")],
        usage=SimpleNamespace(**usage_kwargs),
    )


def _build_call_a_response_json(
    *, input_cluster_ids: list[str], category="패션", cross=True
) -> str:
    return json.dumps(
        {
            "clusters": [
                {
                    "input_cluster_ids": input_cluster_ids,
                    "category_confirmed": category,
                    "canonical_entity_ko": "자라 AI 생성 캠페인",
                    "is_cross_lingual_merge": cross,
                    "key_entities": ["Zara", "AI 생성 캠페인"],
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# Test 1: Call A request carries cache_control (AC10a)
# ---------------------------------------------------------------------------


def test_call_a_cache_control_present():
    """The system block on the Call A request must have cache_control=ephemeral."""
    a1 = _make_article(aid="art_001", title="Zara launches AI campaign", language="en")
    a2 = _make_article(aid="art_002", title="자라 AI 캠페인 공개", language="ko")
    c1 = _make_candidate(cid="cand_001", article_ids=["art_001"], language="en")
    c2 = _make_candidate(cid="cand_002", article_ids=["art_002"], language="ko")
    articles_by_id = {"art_001": a1, "art_002": a2}

    captured_requests: list[dict] = []

    def fake_create(**kwargs):
        captured_requests.append(kwargs)
        return _mock_response(
            _build_call_a_response_json(input_cluster_ids=["cand_001", "cand_002"])
        )

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create = MagicMock(side_effect=fake_create)
        client = LLMClient(api_key="sk-fake")
        client.call_a([c1, c2], articles_by_id)

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert "system" in req
    sys_block = req["system"]
    assert isinstance(sys_block, list) and len(sys_block) == 1
    assert sys_block[0]["type"] == "text"
    assert sys_block[0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Test 2: Call B request carries cache_control (AC10a)
# ---------------------------------------------------------------------------


def test_call_b_cache_control_present():
    """The system block on the Call B request must have cache_control=ephemeral."""
    art = _make_article(aid="art_100", title="샘플 기사")
    ki = KeyIssue(
        cluster_id="cluster_0001",
        category="패션",
        canonical_entity_ko="자라 AI 생성 캠페인",
        primary_entity="Zara",
        novelty_score=0.8,
        diffusion_score=0.6,
        combined_score=0.7,
        article_bundle=[art],
    )

    # Inline minimal mock response — references only cluster_0001 so the
    # Call B semantic validator accepts it. The dry-run pipeline uses a
    # richer shared fixture, which would fail this single-KeyIssue test.
    mock_b = json.dumps(
        {
            "schema_version": "v2",
            "exec_summary_ko": ["요약 1", "요약 2", "요약 3"],
            "sections": {
                "패션": [
                    {
                        "cluster_id": "cluster_0001",
                        "title_ko": "자라 생성형 캠페인",
                        "summary_ko": "자라가 AI 생성 이미지로 캠페인을 교체했다는 내용의 요약이다.",
                        "is_paywalled": False,
                    }
                ]
            },
            "misc_observations_ko": None,
            "insight_box_ko": "AI가 소비재 산업의 비용 구조를 재정의하고 있다는 관찰이다.",
        },
        ensure_ascii=False,
    )

    captured_requests: list[dict] = []

    def fake_create(**kwargs):
        captured_requests.append(kwargs)
        return _mock_response(mock_b)

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create = MagicMock(side_effect=fake_create)
        client = LLMClient(api_key="sk-fake")
        client.call_b([ki], misc=[], today_iso="2026-04-18")

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert "system" in req
    sys_block = req["system"]
    assert sys_block[0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Test 3: merge_candidate_clusters — category-span violation (R1)
# ---------------------------------------------------------------------------


def test_merge_candidate_clusters_category_span_violation():
    """3 pre-cluster categories → unfold and log category_span_violation."""
    a1 = _make_article(aid="art_f", category="식음료")
    a2 = _make_article(aid="art_b", category="뷰티")
    a3 = _make_article(aid="art_s", category="패션")
    c1 = _make_candidate(cid="cand_001", article_ids=["art_f"], category="식음료")
    c2 = _make_candidate(cid="cand_002", article_ids=["art_b"], category="뷰티")
    c3 = _make_candidate(cid="cand_003", article_ids=["art_s"], category="패션")
    articles_by_id = {"art_f": a1, "art_b": a2, "art_s": a3}

    call_a = CallAResponse.model_validate(
        {
            "clusters": [
                {
                    "input_cluster_ids": ["cand_001", "cand_002", "cand_003"],
                    "category_confirmed": "식음료",
                    "canonical_entity_ko": "잘못된 병합",
                    "is_cross_lingual_merge": False,
                    "key_entities": ["Brand"],
                }
            ]
        }
    )
    run_notes: list[str] = []
    result = merge_candidate_clusters([c1, c2, c3], call_a, articles_by_id, run_notes)

    # 3 unfolded clusters, one per candidate
    assert len(result) == 3
    assert any("category_span_violation" in n for n in run_notes)
    # Each unfolded cluster is non-cross-lingual
    for cluster in result:
        assert cluster.is_cross_lingual_merge is False
    # Categories preserved from originals. Python string ordering on
    # Hangul code points yields ["뷰티", "식음료", "패션"].
    cats = sorted(c.category for c in result)
    assert cats == ["뷰티", "식음료", "패션"]


# ---------------------------------------------------------------------------
# Test 4: merge_candidate_clusters — time-span violation (R1)
# ---------------------------------------------------------------------------


def test_merge_candidate_clusters_time_span_violation():
    """Articles 80h apart merged → unfold and log time_span_violation."""
    base = _now()
    a1 = _make_article(aid="art_1", category="패션", published_at=base)
    a2 = _make_article(aid="art_2", category="패션", published_at=base + timedelta(hours=80))
    c1 = _make_candidate(cid="cand_001", article_ids=["art_1"], category="패션", language="en")
    c2 = _make_candidate(cid="cand_002", article_ids=["art_2"], category="패션", language="ko")
    articles_by_id = {"art_1": a1, "art_2": a2}

    call_a = CallAResponse.model_validate(
        {
            "clusters": [
                {
                    "input_cluster_ids": ["cand_001", "cand_002"],
                    "category_confirmed": "패션",
                    "canonical_entity_ko": "시간 초과 병합",
                    "is_cross_lingual_merge": True,
                    "key_entities": ["Zara"],
                }
            ]
        }
    )
    run_notes: list[str] = []
    result = merge_candidate_clusters([c1, c2], call_a, articles_by_id, run_notes)

    assert len(result) == 2  # unfolded
    assert any("time_span_violation" in n for n in run_notes)
    for cluster in result:
        assert cluster.is_cross_lingual_merge is False


# ---------------------------------------------------------------------------
# Test 5: merge_candidate_clusters — valid cross-lingual merge
# ---------------------------------------------------------------------------


def test_merge_candidate_clusters_valid_cross_lingual():
    """2 Fashion candidates (EN+KO) within 24h → merge into single Cluster."""
    base = _now()
    a1 = _make_article(aid="art_en", language="en", category="패션", published_at=base)
    a2 = _make_article(
        aid="art_ko", language="ko", category="패션", published_at=base + timedelta(hours=10)
    )
    c1 = _make_candidate(cid="cand_001", article_ids=["art_en"], category="패션", language="en")
    c2 = _make_candidate(cid="cand_002", article_ids=["art_ko"], category="패션", language="ko")
    articles_by_id = {"art_en": a1, "art_ko": a2}

    call_a = CallAResponse.model_validate(
        {
            "clusters": [
                {
                    "input_cluster_ids": ["cand_001", "cand_002"],
                    "category_confirmed": "패션",
                    "canonical_entity_ko": "자라 AI 생성 캠페인",
                    "is_cross_lingual_merge": True,
                    "key_entities": ["Zara"],
                }
            ]
        }
    )
    run_notes: list[str] = []
    result = merge_candidate_clusters([c1, c2], call_a, articles_by_id, run_notes)

    assert len(result) == 1
    merged = result[0]
    assert merged.is_cross_lingual_merge is True
    assert set(merged.article_ids) == {"art_en", "art_ko"}
    assert merged.canonical_entity_ko == "자라 AI 생성 캠페인"
    assert merged.primary_entity == "Zara"
    assert not run_notes  # no violations


# ---------------------------------------------------------------------------
# Test 6: finalize_sections — Blocker-3 single-cluster category
# ---------------------------------------------------------------------------


def test_finalize_sections_blocker3_one_cluster_category():
    """Food has 1 above threshold, Beauty has 3 above threshold → both sections present."""
    art = _make_article()
    articles_by_id = {art.id: art}

    def _c(cat: str, score: float) -> Cluster:
        return Cluster(
            id=str(uuid.uuid4()),
            category=cat,
            canonical_entity_ko=f"{cat} cluster",
            primary_entity="Entity",
            article_ids=[art.id],
            is_cross_lingual_merge=False,
            diffusion_score=0.5,
            novelty_score=0.5,
            combined_score=score,
        )

    clusters = [
        _c("식음료", 0.50),  # single, above threshold
        _c("뷰티", 0.70),
        _c("뷰티", 0.55),
        _c("뷰티", 0.40),  # still above 0.35
    ]
    result = finalize_sections(clusters, articles_by_id, threshold=0.35, max_per_cat=3)

    sections = result["sections"]
    assert set(sections.keys()) == {"식음료", "뷰티"}
    assert len(sections["식음료"]) == 1
    assert len(sections["뷰티"]) == 3
    # Food must NOT be in misc
    misc_cluster_ids = {ki.cluster_id for ki in result["misc"]}
    food_cluster_ids = {ki.cluster_id for ki in sections["식음료"]}
    assert food_cluster_ids.isdisjoint(misc_cluster_ids)


# ---------------------------------------------------------------------------
# Test 7: finalize_sections — misc overflow (all below threshold)
# ---------------------------------------------------------------------------


def test_finalize_sections_misc_overflow():
    """5 clusters all at 0.2 (< 0.35) → misc has at most 3, sorted desc."""
    art = _make_article()
    articles_by_id = {art.id: art}

    clusters = [
        Cluster(
            id=f"c_{i}",
            category="패션",
            canonical_entity_ko=f"c{i}",
            primary_entity="E",
            article_ids=[art.id],
            is_cross_lingual_merge=False,
            diffusion_score=0.1,
            novelty_score=0.3,
            combined_score=0.2 + i * 0.01,
        )
        for i in range(5)
    ]
    result = finalize_sections(clusters, articles_by_id, threshold=0.35, max_per_cat=3)

    assert result["sections"] == {}
    assert len(result["misc"]) == 3
    # Sorted descending by combined_score
    scores = [ki.combined_score for ki in result["misc"]]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Test 8: AC14 — pydantic extra="forbid" rejects fabricated score field
# ---------------------------------------------------------------------------


def test_call_b_pydantic_extra_forbid_ac14():
    """Injecting novelty_score into a BriefingItem → pydantic.ValidationError."""
    fabricated = {
        "schema_version": "v2",
        "exec_summary_ko": ["line1", "line2", "line3"],
        "sections": {
            "패션": [
                {
                    "cluster_id": "cluster_0001",
                    "title_ko": "제목",
                    "summary_ko": "요약입니다.",
                    "is_paywalled": False,
                    "novelty_score": 0.9,
                }
            ]
        },
        "misc_observations_ko": None,
        "insight_box_ko": "통찰입니다.",
    }
    with pytest.raises(pydantic.ValidationError):
        LLMBriefing.model_validate(fabricated)


# ---------------------------------------------------------------------------
# Test 9: Call A HTTP abort (R3)
# ---------------------------------------------------------------------------


def test_call_a_http_abort(tmp_path, monkeypatch):
    """APIConnectionError twice → SystemExit(3) + call_a_raw.txt persisted."""
    a1 = _make_article(aid="art_001")
    c1 = _make_candidate(cid="cand_001", article_ids=["art_001"])

    # Redirect run dir to tmp
    monkeypatch.setattr(sz, "_RUN_STATE_DIR", tmp_path)

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def always_raise(**kwargs):
        raise APIConnectionError(request=req)

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create = MagicMock(side_effect=always_raise)
        # Speed up retry sleep
        with patch("time.sleep", return_value=None):
            client = LLMClient(api_key="sk-fake", run_dir=tmp_path / "run_test")
            with pytest.raises(SystemExit) as exc_info:
                client.call_a([c1], {"art_001": a1})
    assert exc_info.value.code == 3
    raw_file = tmp_path / "run_test" / "call_a_raw.txt"
    assert raw_file.exists()


# ---------------------------------------------------------------------------
# Test 10: Call A schema retry then abort
# ---------------------------------------------------------------------------


def test_call_a_schema_retry_then_abort(tmp_path):
    """Invalid JSON twice → SystemExit(3) + raw file persisted."""
    a1 = _make_article(aid="art_001")
    c1 = _make_candidate(cid="cand_001", article_ids=["art_001"])

    bad = _mock_response("this is not json at all {{{")

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create = MagicMock(return_value=bad)
        client = LLMClient(api_key="sk-fake", run_dir=tmp_path / "run_test")
        with pytest.raises(SystemExit) as exc_info:
            client.call_a([c1], {"art_001": a1})
    assert exc_info.value.code == 3
    raw_file = tmp_path / "run_test" / "call_a_raw.txt"
    assert raw_file.exists()
    assert "this is not json" in raw_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 11: Call B Hangul ratio fail
# ---------------------------------------------------------------------------


def test_call_b_hangul_ratio_fail(tmp_path):
    """summary_ko with 50% English → semantic validation fails, then abort."""
    art = _make_article(aid="art_1")
    ki = KeyIssue(
        cluster_id="cluster_0001",
        category="패션",
        canonical_entity_ko="자라",
        primary_entity="Zara",
        novelty_score=0.8,
        diffusion_score=0.6,
        combined_score=0.7,
        article_bundle=[art],
    )

    # summary_ko dominated by Latin characters → Hangul ratio < 0.80
    bad_briefing = json.dumps(
        {
            "schema_version": "v2",
            "exec_summary_ko": ["첫째 줄 한국어", "둘째 줄 한국어", "셋째 줄 한국어"],
            "sections": {
                "패션": [
                    {
                        "cluster_id": "cluster_0001",
                        "title_ko": "Zara launches campaign today",
                        "summary_ko": "Zara launched a new campaign this week with AI models and new technology everywhere",
                        "is_paywalled": False,
                    }
                ]
            },
            "misc_observations_ko": None,
            "insight_box_ko": "통찰입니다. 의미 있는 한국어 문장입니다.",
        }
    )

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create = MagicMock(
            return_value=_mock_response(bad_briefing)
        )
        client = LLMClient(api_key="sk-fake", run_dir=tmp_path / "run_test")
        with pytest.raises(SystemExit) as exc_info:
            client.call_b([ki], misc=[], today_iso="2026-04-18")
    assert exc_info.value.code == 4
    raw_file = tmp_path / "run_test" / "call_b_response_raw.json"
    assert raw_file.exists()


# ---------------------------------------------------------------------------
# Test 12: dry-run loads fixtures, no network
# ---------------------------------------------------------------------------


def test_dry_run_loads_fixtures(tmp_path):
    """run_summarizer(..., dry_run=True) returns a valid LLMBriefing without network."""
    db_path = tmp_path / "briefing.db"
    conn = bootstrap(db_path)
    today = _now()
    run_id = "run_test_001"
    insert_run(conn, run_id, today)

    # Build candidates matching fixture IDs cand_001, cand_002
    base = _now()
    a1 = _make_article(
        aid="art_en_001",
        title="Zara launches AI-generated campaign",
        language="en",
        category="패션",
        source_name="Business of Fashion",
        source_type="SpecializedMedia",
        published_at=base,
        extracted_entities=["Zara"],
    )
    a2 = _make_article(
        aid="art_ko_001",
        title="자라, AI 생성 캠페인 공개",
        language="ko",
        category="패션",
        source_name="패션비즈",
        source_type="TraditionalMedia",
        published_at=base + timedelta(hours=2),
        extracted_entities=["Zara"],
    )
    c1 = _make_candidate(
        cid="cand_001",
        article_ids=["art_en_001"],
        category="패션",
        language="en",
        rep_title="Zara launches AI-generated campaign",
    )
    c2 = _make_candidate(
        cid="cand_002",
        article_ids=["art_ko_001"],
        category="패션",
        language="ko",
        rep_title="자라, AI 생성 캠페인 공개",
    )
    articles_by_id = {"art_en_001": a1, "art_ko_001": a2}
    scored_candidates = [
        (c1, 1.0, 0.5, 0.7),
        (c2, 1.0, 0.5, 0.7),
    ]

    # The anthropic client must never be called in dry_run
    with patch("anthropic.Anthropic") as MockClient:
        mock_create = MagicMock()
        MockClient.return_value.messages.create = mock_create

        briefing, key_issues, run_notes, usage = run_summarizer(
            conn,
            scored_candidates,
            articles_by_id,
            today,
            run_id,
            dry_run=True,
            api_key="sk-fake",
        )

        # Zero network calls
        assert mock_create.call_count == 0

    assert isinstance(briefing, LLMBriefing)
    assert briefing.schema_version == "v2"
    assert len(briefing.exec_summary_ko) == 3
    assert usage["call_a"]["input_tokens"] == 0
    assert usage["call_b"]["input_tokens"] == 0
    # A merged cluster should be in DB
    rows = conn.execute("SELECT id, is_cross_lingual_merge FROM clusters").fetchall()
    assert len(rows) == 1
    assert rows[0]["is_cross_lingual_merge"] == 1


# ---------------------------------------------------------------------------
# Extra test 13: Call A coverage retry path
# ---------------------------------------------------------------------------


def test_call_a_coverage_retry_succeeds():
    """First response misses a cluster, retry response covers all → success."""
    a1 = _make_article(aid="art_001")
    a2 = _make_article(aid="art_002")
    c1 = _make_candidate(cid="cand_001", article_ids=["art_001"])
    c2 = _make_candidate(cid="cand_002", article_ids=["art_002"])
    articles_by_id = {"art_001": a1, "art_002": a2}

    bad = _mock_response(
        _build_call_a_response_json(input_cluster_ids=["cand_001"])  # missing cand_002
    )
    good = _mock_response(
        _build_call_a_response_json(input_cluster_ids=["cand_001", "cand_002"])
    )

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create = MagicMock(side_effect=[bad, good])
        client = LLMClient(api_key="sk-fake")
        resp, usage = client.call_a([c1, c2], articles_by_id)

    assert len(resp.clusters) == 1
    assert set(resp.clusters[0].input_cluster_ids) == {"cand_001", "cand_002"}
