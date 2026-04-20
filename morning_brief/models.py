"""Pydantic models for morning_brief: domain models and LLM response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# -------- Shared type aliases --------

# Language codes supported across the collector/pipeline. Widened from
# ("ko", "en") to the 5-language set required by PR-1 (plan v2 §A5a/A5b).
Language = Literal["ko", "en", "ja", "zh", "es"]

# Category canonical values (plan v2 §D10-A). Renamed from
# {Food, Beauty, Fashion, Living, Hospitality} to the 6-way Korean canonical
# set. Hospitality is absorbed into 라이프스타일.
#
# Post-PR-2 QA (Issue C): 식음료 is the new canonical label for food &
# beverage; the legacy "F&B" token remains an accepted Literal value so
# pre-migration briefing.db rows + EML-renderer fixtures still validate.
# The site renderer adapter and all new fixtures use "식음료". The one-shot
# ``scripts/migrate_categories.py`` rewrites stored "F&B" values to "식음료".
Category = Literal[
    "식음료",
    "F&B",
    "뷰티",
    "패션",
    "라이프스타일",
    "소비트렌드",
    "MacroTrends",
]

# SCTEEP macro-classification dimensions (MacroTab — plan v2 §D2-D).
# Used by macro_tagger in PR-2; added here so downstream code can reference
# the alias during PR-1 without importing it twice.
SceepDimension = Literal[
    "Social",
    "Culture",
    "Technology",
    "Economy",
    "Environment",
    "Politics",
]

# Company-tag class (plan v2 §D3). 3-class schema for companies.yml entries.
CompanyClass = Literal["대기업", "유통", "혁신스타트업"]


# -------- Domain models (internal; permit extras by default) --------


class CompanyTag(BaseModel):
    """A company match emitted by the collector for an Article.

    The ``class`` field is a Python keyword, so it is exposed via the
    ``class_`` attribute and the ``class`` alias for JSON round-tripping.
    Strict (``extra='forbid'``) so collector bugs surface immediately.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    class_: CompanyClass = Field(alias="class")
    confidence: float  # 0.0–1.0


class Article(BaseModel):
    """A single news article fetched from an RSS source."""

    id: str
    title: str
    source_name: str
    source_type: Literal["TraditionalMedia", "SpecializedMedia", "CuratedTrendReport"]
    url: str
    canonical_url: str
    language: Language
    published_at: datetime
    category: str | None
    raw_summary: str
    enriched_text: str | None
    fetched_at: datetime
    extracted_entities: list[str]
    company_tags: list[CompanyTag] = Field(default_factory=list)
    # ISO-3166 alpha-3 country code carried from sources.yml, used by the
    # site renderer to render a per-card flag. ``None`` means "fall back to
    # the language-based default map" (plan v2 PR-3 Task 3).
    source_country: str | None = None


class CandidateCluster(BaseModel):
    """A pre-cluster group of articles sharing an entity, before Call A."""

    id: str
    category: str
    article_ids: list[str]
    representative_title: str
    language: Language


class Cluster(BaseModel):
    """A merged cluster after merge_candidate_clusters() and sanity checks."""

    id: str
    category: str
    canonical_entity_ko: str
    primary_entity: str
    article_ids: list[str]
    is_cross_lingual_merge: bool
    diffusion_score: float
    novelty_score: float
    combined_score: float
    sceep_dimensions: list[SceepDimension] = Field(default_factory=list)


class KeyIssue(BaseModel):
    """A top-ranked cluster selected for inclusion in the briefing."""

    cluster_id: str
    category: str
    canonical_entity_ko: str
    primary_entity: str
    novelty_score: float
    diffusion_score: float
    combined_score: float
    article_bundle: list[Article]
    # SCTEEP dimensions copied from the source Cluster (MacroTab cards only;
    # plan v2 PR-3 Task 1). Industry KeyIssues always leave this empty.
    sceep_dimensions: list[SceepDimension] = Field(default_factory=list)


# -------- LLM response models (STRICT: extra="forbid") --------


class CallAClusterOut(BaseModel):
    """LLM output for a single cluster from Call A (clustering step)."""

    model_config = ConfigDict(extra="forbid")

    input_cluster_ids: list[str]
    category_confirmed: Category
    canonical_entity_ko: str
    is_cross_lingual_merge: bool
    key_entities: list[str]


class CallAResponse(BaseModel):
    """Full LLM response from Call A containing all cluster outputs."""

    model_config = ConfigDict(extra="forbid")

    clusters: list[CallAClusterOut]


class BriefingItem(BaseModel):
    """A single briefing entry for one cluster, produced by Call B."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    title_ko: str
    summary_ko: str
    is_paywalled: bool


class LLMBriefing(BaseModel):
    """Full structured briefing produced by Call B."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v2"]
    exec_summary_ko: list[str] = Field(min_length=3, max_length=3)
    sections: dict[Category, list[BriefingItem]]
    misc_observations_ko: list[BriefingItem] | None
    insight_box_ko: str

    @field_validator("exec_summary_ko")
    @classmethod
    def exactly_three_items(cls, v: list[str]) -> list[str]:
        """Enforce exactly 3 executive summary lines."""
        if len(v) != 3:
            raise ValueError(f"exec_summary_ko must have exactly 3 items, got {len(v)}")
        return v
