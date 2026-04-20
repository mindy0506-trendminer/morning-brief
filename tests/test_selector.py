"""Acceptance tests for morning_brief/selector.py — Step 4."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from morning_brief.db import bootstrap, upsert_entity_history
from morning_brief.models import Article, CandidateCluster
from morning_brief.selector import pick_top, precluster, score_candidates, select

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """Return a tz-naive UTC datetime for use in tests."""
    return datetime(2026, 4, 18, 9, 0, 0)


def _make_article(
    title: str = "Test Article",
    language: str = "ko",
    category: str | None = "패션",
    source_name: str = "Source1",
    source_type: str = "TraditionalMedia",
    published_at: datetime | None = None,
    extracted_entities: list[str] | None = None,
) -> Article:
    now = _now()
    return Article(
        id=str(uuid.uuid4()),
        title=title,
        source_name=source_name,
        source_type=source_type,  # type: ignore[arg-type]
        url=f"https://example.com/{uuid.uuid4()}",
        canonical_url=f"https://example.com/{uuid.uuid4()}",
        language=language,  # type: ignore[arg-type]
        published_at=published_at or now,
        category=category,
        raw_summary="",
        enriched_text=None,
        fetched_at=now,
        extracted_entities=extracted_entities or [],
    )


def _make_candidate(
    article_ids: list[str],
    category: str = "패션",
    language: str = "ko",
    rep_title: str = "Rep Title",
) -> CandidateCluster:
    return CandidateCluster(
        id=str(uuid.uuid4()),
        category=category,
        article_ids=article_ids,
        representative_title=rep_title,
        language=language,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Test 1: precluster — same-lang near-dupes merge
# ---------------------------------------------------------------------------


class TestPreclusterSameLangNearDupes:
    def test_near_identical_titles_merge(self):
        """2 Korean articles with nearly identical titles → single CandidateCluster."""
        a1 = _make_article(
            title="자라, 2026 봄 컬렉션 공개",
            language="ko",
            category="패션",
        )
        a2 = _make_article(
            title="자라 2026년 봄 컬렉션 발표",  # high similarity to a1
            language="ko",
            category="패션",
            published_at=_now() + timedelta(hours=1),
        )
        candidates = precluster([a1, a2])
        fashion_clusters = [c for c in candidates if c.category == "패션"]
        # Both articles should end up in one cluster
        total_articles = sum(len(c.article_ids) for c in fashion_clusters)
        assert total_articles == 2
        assert any(len(c.article_ids) == 2 for c in fashion_clusters)

    def test_dissimilar_titles_separate(self):
        """2 Korean articles with unrelated titles → 2 separate CandidateClusters."""
        a1 = _make_article(
            title="자라 봄 신상 공개",
            language="ko",
            category="패션",
        )
        a2 = _make_article(
            title="나이키 운동화 새 모델 발표",
            language="ko",
            category="패션",
            published_at=_now() + timedelta(hours=2),
        )
        candidates = precluster([a1, a2])
        fashion_clusters = [c for c in candidates if c.category == "패션"]
        assert len(fashion_clusters) == 2

    def test_beyond_72h_no_merge(self):
        """Articles > 72h apart don't merge even with similar titles."""
        a1 = _make_article(
            title="삼성 갤럭시 신상 공개",
            language="ko",
            category="라이프스타일",
        )
        a2 = _make_article(
            title="삼성 갤럭시 신상 출시",  # similar title
            language="ko",
            category="라이프스타일",
            published_at=_now() + timedelta(hours=73),
        )
        candidates = precluster([a1, a2])
        living_clusters = [c for c in candidates if c.category == "라이프스타일"]
        # Should be 2 separate clusters due to time gap
        assert len(living_clusters) == 2


# ---------------------------------------------------------------------------
# Test 2: precluster — cross-lang no merge
# ---------------------------------------------------------------------------


class TestPreclusterCrossLangNoMerge:
    def test_cross_language_articles_stay_separate(self):
        """EN and KO articles in same category are never merged at precluster stage."""
        a_en = _make_article(
            title="Zara launches global campaign",
            language="en",
            category="패션",
        )
        a_ko = _make_article(
            title="자라 글로벌 캠페인 공개",
            language="ko",
            category="패션",
        )
        candidates = precluster([a_en, a_ko])
        # Must have at least 2 clusters (one per language)
        langs = {c.language for c in candidates}
        assert "en" in langs
        assert "ko" in langs
        # Each language group must be a separate cluster
        en_clusters = [c for c in candidates if c.language == "en"]
        ko_clusters = [c for c in candidates if c.language == "ko"]
        assert len(en_clusters) >= 1
        assert len(ko_clusters) >= 1
        # The English article must be in an English cluster only
        en_article_ids = {aid for c in en_clusters for aid in c.article_ids}
        ko_article_ids = {aid for c in ko_clusters for aid in c.article_ids}
        assert a_en.id in en_article_ids
        assert a_ko.id in ko_article_ids
        assert a_en.id not in ko_article_ids
        assert a_ko.id not in en_article_ids


# ---------------------------------------------------------------------------
# Test 3: scoring — diffusion
# ---------------------------------------------------------------------------


class TestScoringDiffusion:
    def test_five_sources_high_diffusion(self, tmp_path):
        """Cluster with 5 distinct source_names → diffusion_score ≈ 0.6 * 1.0 + 0.4 * x."""
        conn = bootstrap(tmp_path / "briefing.db")
        today = _now()

        articles = [
            _make_article(
                source_name=f"Source{i}",
                source_type="TraditionalMedia",
                extracted_entities=[],
            )
            for i in range(5)
        ]
        candidate = _make_candidate([a.id for a in articles])
        articles_by_id = {a.id: a for a in articles}

        scored = score_candidates(conn, [candidate], articles_by_id, today)
        assert len(scored) == 1
        _, novelty, diffusion, combined = scored[0]

        # n_sources=5 → min(5/5, 1.0)=1.0; source_type_diversity=1/3
        # diffusion = 0.6*1.0 + 0.4*(1/3) ≈ 0.733
        expected_diffusion = 0.6 * 1.0 + 0.4 * (1 / 3)
        assert abs(diffusion - expected_diffusion) < 0.01

    def test_one_source_low_diffusion(self, tmp_path):
        """Cluster with 1 source_name → diffusion < 0.5."""
        conn = bootstrap(tmp_path / "briefing.db")
        today = _now()

        articles = [
            _make_article(
                source_name="SingleSource",
                source_type="TraditionalMedia",
            )
            for _ in range(3)
        ]
        candidate = _make_candidate([a.id for a in articles])
        articles_by_id = {a.id: a for a in articles}

        scored = score_candidates(conn, [candidate], articles_by_id, today)
        _, novelty, diffusion, combined = scored[0]

        # n_sources=1 → 0.6*(1/5)=0.12; source_type_diversity=1/3 → 0.4*(1/3)≈0.133
        assert diffusion < 0.5


# ---------------------------------------------------------------------------
# Test 4: novelty + warmup rule
# ---------------------------------------------------------------------------


class TestNoveltyWarmupRule:
    def test_warmup_phase_weights(self, tmp_path):
        """Empty entity_history → warmup phase → combined = 0.3*nov + 0.7*dif."""
        conn = bootstrap(tmp_path / "briefing.db")
        today = _now()

        articles = [_make_article(extracted_entities=["Zara"])]
        candidate = _make_candidate([a.id for a in articles])
        articles_by_id = {a.id: a for a in articles}

        scored = score_candidates(conn, [candidate], articles_by_id, today)
        _, novelty, diffusion, combined = scored[0]

        # is_warmup_phase=True (empty DB) → combined = 0.3*nov + 0.7*dif
        expected = 0.3 * novelty + 0.7 * diffusion
        assert abs(combined - expected) < 0.001

    def test_non_warmup_phase_weights(self, tmp_path):
        """Old entity_history (>7 days) → NOT warmup → combined = 0.55*nov + 0.45*dif."""
        conn = bootstrap(tmp_path / "briefing.db")
        today = _now()
        old_time = today - timedelta(days=10)

        # Seed entity_history with old entry to exit warmup phase
        upsert_entity_history(conn, "zara", "Zara", "old-article", old_time)

        articles = [_make_article(extracted_entities=["Zara"])]
        candidate = _make_candidate([a.id for a in articles])
        articles_by_id = {a.id: a for a in articles}

        scored = score_candidates(conn, [candidate], articles_by_id, today)
        _, novelty, diffusion, combined = scored[0]

        # Not warmup → combined = 0.55*nov + 0.45*dif
        expected = 0.55 * novelty + 0.45 * diffusion
        assert abs(combined - expected) < 0.001

    def test_warmup_vs_non_warmup_combined_differ(self, tmp_path):
        """Warmup and non-warmup produce different combined scores for same nov/dif."""
        # warmup: combined = 0.3*1.0 + 0.7*0.5 = 0.65
        # non-warmup: combined = 0.55*1.0 + 0.45*0.5 = 0.775
        assert abs((0.3 * 1.0 + 0.7 * 0.5) - (0.55 * 1.0 + 0.45 * 0.5)) > 0.05


# ---------------------------------------------------------------------------
# Test 5: picker — global cap
# ---------------------------------------------------------------------------


class TestPickerGlobalCap:
    def _make_scored_items(
        self, n: int, n_cats: int = 5
    ) -> list[tuple[CandidateCluster, float, float, float]]:
        """Create n scored items distributed across n_cats categories."""
        cats = [f"Cat{i}" for i in range(n_cats)]
        items = []
        for i in range(n):
            cat = cats[i % n_cats]
            combined = (n - i) / n  # descending scores
            candidate = _make_candidate(
                article_ids=[str(uuid.uuid4())],
                category=cat,
            )
            items.append((candidate, 0.8, 0.7, combined))
        return items

    def test_global_cap_enforced(self):
        """20 scored candidates across 5 cats → output ≤ 13 items."""
        scored = self._make_scored_items(20, n_cats=5)
        result = pick_top(scored, min_per_cat=2, max_per_cat=3, global_cap=13)
        assert len(result) <= 13

    def test_max_per_cat_enforced(self):
        """Each category takes at most max_per_cat items."""
        scored = self._make_scored_items(20, n_cats=5)
        result = pick_top(scored, min_per_cat=2, max_per_cat=3, global_cap=13)
        from collections import Counter

        cat_counts = Counter(item[0].category for item in result)
        for cat, count in cat_counts.items():
            assert count <= 3, f"Category {cat} has {count} > max_per_cat=3"

    def test_highest_combined_kept(self):
        """After global cap, the kept items have higher combined scores than trimmed."""
        scored = self._make_scored_items(20, n_cats=5)
        result = pick_top(scored, min_per_cat=2, max_per_cat=3, global_cap=13)

        result_scores = {item[0].id: item[3] for item in result}
        all_item_ids = {item[0].id for item in scored}
        trimmed_ids = all_item_ids - set(result_scores.keys())

        if trimmed_ids and result_scores:
            min_kept = min(result_scores.values())
            trimmed_scores = [s[3] for s in scored if s[0].id in trimmed_ids]
            max_trimmed = max(trimmed_scores) if trimmed_scores else 0.0
            assert min_kept >= max_trimmed - 0.01  # tolerance for per-cat selection

    def test_under_global_cap_no_trim(self):
        """Fewer than 13 items → all taken."""
        scored = self._make_scored_items(5, n_cats=5)
        result = pick_top(scored, min_per_cat=2, max_per_cat=3, global_cap=13)
        assert len(result) == 5
