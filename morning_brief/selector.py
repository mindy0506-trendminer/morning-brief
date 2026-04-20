"""Selector: pre-cluster, score, and pick top CandidateClusters."""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from rapidfuzz import fuzz

from morning_brief.db import is_warmup_phase, query_entity_prior_days
from morning_brief.models import Article, CandidateCluster

logger = logging.getLogger(__name__)

# Similarity threshold for title matching (single-linkage)
_TITLE_SIMILARITY_THRESHOLD = 75
# Maximum age difference (hours) for articles to be in the same clustering pool
_POOL_WINDOW_HOURS = 72

# ---------------------------------------------------------------------------
# Pre-cluster
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, NFC-normalize for comparison."""
    t = unicodedata.normalize("NFC", title).lower()
    return _PUNCT_RE.sub("", t).strip()


def precluster(
    articles: list[Article],
    dry_run: bool = False,
) -> list[CandidateCluster]:
    """Group articles into CandidateCluster objects by category + language + 72h window.

    Uses single-linkage clustering with rapidfuzz token_set_ratio ≥ 75 on titles.
    When ``dry_run`` is True, cluster IDs are assigned deterministically as
    ``cand_001``, ``cand_002``, ... in the order they are produced (stable across
    runs for fixture-based tests). Otherwise UUIDv4 strings are used.
    """
    # Group by (category, language)
    groups: dict[tuple[str, str], list[Article]] = {}
    for article in articles:
        cat = article.category or "Uncategorized"
        key = (cat, article.language)
        groups.setdefault(key, []).append(article)

    clusters: list[CandidateCluster] = []
    _counter = 0

    for (cat, lang), group in groups.items():
        # Sort by published_at ascending so earliest = representative
        sorted_group = sorted(group, key=lambda a: a.published_at)
        # Single-linkage: assign each article to first cluster it matches
        # cluster_members: list of list[Article]
        cluster_buckets: list[list[Article]] = []

        for article in sorted_group:
            title_norm = _normalize_title(article.title)
            placed = False
            for bucket in cluster_buckets:
                # Check 72h window against earliest article in bucket
                earliest = bucket[0]
                time_diff = abs(
                    (article.published_at - earliest.published_at).total_seconds()
                )
                if time_diff > _POOL_WINDOW_HOURS * 3600:
                    continue
                # Check title similarity against any member (single-linkage)
                for member in bucket:
                    member_norm = _normalize_title(member.title)
                    score = fuzz.token_set_ratio(title_norm, member_norm)
                    if score >= _TITLE_SIMILARITY_THRESHOLD:
                        bucket.append(article)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                cluster_buckets.append([article])

        for bucket in cluster_buckets:
            representative = min(bucket, key=lambda a: a.published_at)
            if dry_run:
                _counter += 1
                cid = f"cand_{_counter:03d}"
            else:
                cid = str(uuid.uuid4())
            candidate = CandidateCluster(
                id=cid,
                category=cat,
                article_ids=[a.id for a in bucket],
                representative_title=representative.title,
                language=lang,  # type: ignore[arg-type]
            )
            clusters.append(candidate)

    return clusters


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _normalize_entity(text: str) -> str:
    """Lowercase + NFC normalize."""
    return unicodedata.normalize("NFC", text).lower()


def score_candidates(
    conn: Any,
    candidates: list[CandidateCluster],
    articles_by_id: dict[str, Article],
    today: datetime,
) -> list[tuple[CandidateCluster, float, float, float]]:
    """Score each candidate cluster and return (candidate, novelty, diffusion, combined) tuples."""
    warmup = is_warmup_phase(conn, today)
    scored: list[tuple[CandidateCluster, float, float, float]] = []

    for candidate in candidates:
        art_ids = candidate.article_ids
        cluster_articles = [articles_by_id[aid] for aid in art_ids if aid in articles_by_id]

        # Diffusion
        n_sources = len({a.source_name for a in cluster_articles})
        source_types = {a.source_type for a in cluster_articles}
        source_type_diversity = len(source_types) / 3.0
        diffusion = 0.6 * min(n_sources / 5.0, 1.0) + 0.4 * source_type_diversity

        # Primary entity: most frequent across all articles in cluster
        entity_counter: Counter[str] = Counter()
        for art in cluster_articles:
            for ent in art.extracted_entities:
                entity_counter[ent] += 1

        primary_entity: str = ""
        if entity_counter:
            primary_entity = entity_counter.most_common(1)[0][0]

        # Novelty
        prior_days = 0
        if primary_entity:
            norm = _normalize_entity(primary_entity)
            prior_days = query_entity_prior_days(conn, norm, today, days=7)
        novelty = max(0.0, 1.0 - 0.15 * prior_days)
        novelty = min(novelty, 1.0)

        # Combined score with warmup rule
        if warmup:
            combined = 0.3 * novelty + 0.7 * diffusion
        else:
            combined = 0.55 * novelty + 0.45 * diffusion

        scored.append((candidate, novelty, diffusion, combined))

    return scored


# ---------------------------------------------------------------------------
# Picker
# ---------------------------------------------------------------------------


def pick_top(
    scored: list[tuple[CandidateCluster, float, float, float]],
    min_per_cat: int = 2,
    max_per_cat: int = 3,
    global_cap: int = 13,
) -> list[tuple[CandidateCluster, float, float, float]]:
    """Select up to max_per_cat per category, then trim to global_cap by combined score."""
    # Group by category
    by_cat: dict[str, list[tuple[CandidateCluster, float, float, float]]] = {}
    for item in scored:
        cat = item[0].category
        by_cat.setdefault(cat, []).append(item)

    selected: list[tuple[CandidateCluster, float, float, float]] = []

    for cat, items in by_cat.items():
        # Sort by combined desc
        items_sorted = sorted(items, key=lambda t: t[3], reverse=True)
        taken = items_sorted[:max_per_cat]
        if len(items_sorted) < min_per_cat:
            logger.warning(
                "Category %s has fewer than min_per_cat=%d candidates (%d available)",
                cat,
                min_per_cat,
                len(items_sorted),
            )
        selected.extend(taken)

    # Trim to global_cap by lowest combined score
    if len(selected) > global_cap:
        selected.sort(key=lambda t: t[3], reverse=True)
        selected = selected[:global_cap]

    return selected


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def select(
    conn: Any,
    articles: list[Article],
    today: datetime,
    dry_run: bool = False,
) -> list[tuple[CandidateCluster, float, float, float]]:
    """Precluster, score, and pick top candidates.

    Returns list of (CandidateCluster, novelty, diffusion, combined) tuples.
    When ``dry_run`` is True, candidate IDs are assigned deterministically
    (``cand_001``, ``cand_002``, …) so fixtures can reference them stably.
    """
    articles_by_id = {a.id: a for a in articles}
    candidates = precluster(articles, dry_run=dry_run)
    scored = score_candidates(conn, candidates, articles_by_id, today)
    return pick_top(scored)
