"""F8 — SCTEEP assignment via mocked Sonnet response; no-op on missing key."""

from __future__ import annotations

import types

import pytest

from morning_brief.macro_tagger import (
    MAX_CANDIDATES_PER_RUN,
    tag_macro_clusters,
    tag_macro_clusters_dry_run,
    _parse_response,
)
from morning_brief.models import Cluster


def _cluster(cid: str, category: str = "MacroTrends") -> Cluster:
    return Cluster(
        id=cid,
        category=category,
        canonical_entity_ko="테스트",
        primary_entity="Test",
        article_ids=[f"{cid}_a1"],
        is_cross_lingual_merge=False,
        diffusion_score=0.5,
        novelty_score=0.5,
        combined_score=0.5,
        sceep_dimensions=[],
    )


class _MockMessages:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(text=self._response_text)]
        )


class _MockClient:
    def __init__(self, response_text: str):
        self.messages = _MockMessages(response_text)


def test_tag_assigns_dims_to_macro_only():
    clusters = [
        _cluster("m1", "MacroTrends"),
        _cluster("m2", "MacroTrends"),
        _cluster("f1", "패션"),
    ]
    client = _MockClient(
        '{"clusters": ['
        '  {"cluster_id": "m1", "sceep_dimensions": ["Economy", "Politics"]},'
        '  {"cluster_id": "m2", "sceep_dimensions": ["Technology"]}'
        ']}'
    )
    out = tag_macro_clusters(clusters, client=client)
    by_id = {c.id: c for c in out}
    assert by_id["m1"].sceep_dimensions == ["Economy", "Politics"]
    assert by_id["m2"].sceep_dimensions == ["Technology"]
    assert by_id["f1"].sceep_dimensions == []  # industry cluster untouched


def test_tag_respects_cost_guard(monkeypatch):
    # 60 macro clusters — only the first 50 must be sent to the client.
    clusters = [_cluster(f"m{i:02d}") for i in range(60)]
    client = _MockClient('{"clusters": []}')
    tag_macro_clusters(clusters, client=client)
    assert len(client.messages.calls) == 1
    payload = client.messages.calls[0]["messages"][0]["content"]
    # Payload JSON must contain exactly MAX_CANDIDATES_PER_RUN cluster_ids.
    import json as _json
    body = _json.loads(payload)
    assert len(body["clusters"]) == MAX_CANDIDATES_PER_RUN


def test_tag_no_macro_returns_input_unchanged():
    clusters = [_cluster("f1", "패션"), _cluster("b1", "뷰티")]
    out = tag_macro_clusters(clusters, client=_MockClient("{}"))
    assert out == clusters


def test_tag_no_api_key_no_op(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    clusters = [_cluster("m1")]
    # No client + no env var → log warning and return input unchanged.
    out = tag_macro_clusters(clusters, client=None, api_key=None)
    assert out == clusters
    assert out[0].sceep_dimensions == []


def test_tag_client_exception_is_caught():
    class _FailingClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("boom")
    clusters = [_cluster("m1")]
    out = tag_macro_clusters(clusters, client=_FailingClient())
    # Should not raise; dims stay empty.
    assert out[0].sceep_dimensions == []


def test_parse_response_strict_cap_at_three_dims():
    raw = (
        '{"m1": ["Social", "Culture", "Technology", "Economy", "Politics"]}'
    )
    parsed = _parse_response(raw)
    assert parsed["m1"] == ["Social", "Culture", "Technology"]


def test_parse_response_rejects_unknown_dim():
    raw = '{"m1": ["Social", "Unknown", "Technology"]}'
    parsed = _parse_response(raw)
    assert parsed["m1"] == ["Social", "Technology"]


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"m1": ["Social"]}\n```'
    parsed = _parse_response(raw)
    assert parsed == {"m1": ["Social"]}


def test_parse_response_handles_bad_json():
    assert _parse_response("not json at all") == {}


# ---------------------------------------------------------------------------
# PR-3 Task 1 — dry-run deterministic fallback
# ---------------------------------------------------------------------------


def _macro_cluster(cid: str, canonical: str, primary: str) -> Cluster:
    return Cluster(
        id=cid,
        category="MacroTrends",
        canonical_entity_ko=canonical,
        primary_entity=primary,
        article_ids=[f"{cid}_a1"],
        is_cross_lingual_merge=False,
        diffusion_score=0.5,
        novelty_score=0.5,
        combined_score=0.5,
        sceep_dimensions=[],
    )


def test_dry_run_deterministic_fallback_no_api_call():
    """Known keywords map to the expected SCTEEP dimensions offline."""
    clusters = [
        _macro_cluster("m_elec", "미국 대선 영향", "대선 정책"),
        _macro_cluster("m_tech", "AI 반도체 경쟁", "AI 기술"),
        _macro_cluster("m_env", "ESG climate 공시", "climate"),
        _macro_cluster("m_gen", "Gen Z 세대 소비", "Gen Z"),
        # Industry cluster must be left untouched.
        Cluster(
            id="f_ko",
            category="패션",
            canonical_entity_ko="자라 캠페인",
            primary_entity="Zara",
            article_ids=["f_ko_a1"],
            is_cross_lingual_merge=False,
            diffusion_score=0.5,
            novelty_score=0.5,
            combined_score=0.5,
            sceep_dimensions=[],
        ),
    ]
    out = tag_macro_clusters_dry_run(clusters)
    by_id = {c.id: c for c in out}
    # Politics keyword hit via '대선'
    assert "Politics" in by_id["m_elec"].sceep_dimensions
    # Technology keyword hit via 'AI' / '기술'
    assert "Technology" in by_id["m_tech"].sceep_dimensions
    # Environment keyword hit via 'ESG' / 'climate'
    assert "Environment" in by_id["m_env"].sceep_dimensions
    # Social keyword hit via 'Gen Z' / '세대'
    assert "Social" in by_id["m_gen"].sceep_dimensions
    # Industry cluster is not touched by the dry-run fallback either.
    assert by_id["f_ko"].sceep_dimensions == []


def test_dry_run_fallback_assigns_at_least_one_dim():
    """Clusters with no keyword matches still get a default dimension.

    Rationale: the sample site must never ship a MacroTab card with an
    empty badge row — a completely blank macro card looks like a
    rendering bug to the human QA reviewer.
    """
    cluster = _macro_cluster("m_no", "의미 없는 엔티티", "Noop")
    out = tag_macro_clusters_dry_run([cluster])
    assert len(out[0].sceep_dimensions) >= 1

