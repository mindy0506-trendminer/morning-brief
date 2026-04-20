"""Two-call LLM pipeline: Call A (cluster+canonicalize) and Call B (write briefing).

Owns merge_candidate_clusters() with R1 sanity checks, rescore_clusters(),
finalize_sections() with Blocker-3 rule, and top-level run_summarizer().
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

import anthropic
import pydantic
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from morning_brief.db import (
    insert_cluster,
    insert_cluster_members,
    is_warmup_phase,
    query_entity_prior_days,
)
from morning_brief.models import (
    Article,
    CallAResponse,
    CandidateCluster,
    Cluster,
    KeyIssue,
    LLMBriefing,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level paths
# ---------------------------------------------------------------------------

CALL_A_SYSTEM_PATH = Path(__file__).parent / "prompts" / "call_a_system.md"
CALL_A_USER_TEMPLATE = Path(__file__).parent / "prompts" / "call_a_user.j2"
CALL_B_SYSTEM_PATH = Path(__file__).parent / "prompts" / "call_b_system.md"
CALL_B_USER_TEMPLATE = Path(__file__).parent / "prompts" / "call_b_user.j2"

_RUN_STATE_DIR = Path(".omc/state/briefing/runs")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CATEGORY_SPAN_MAX = 2
_TIME_SPAN_MAX_HOURS = 72
_HANGUL_RATIO_MIN = 0.80
_DEFAULT_SECTION_THRESHOLD = 0.35
_DEFAULT_MAX_PER_CAT = 3
_MAX_ARTICLES_PER_BUNDLE = 5
_MISC_CAP = 3
_CATEGORIES: tuple[str, ...] = (
    "식음료",
    "뷰티",
    "패션",
    "라이프스타일",
    "소비트렌드",
    "MacroTrends",
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CJK_OTHER_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_URL_TOKEN_RE = re.compile(r"https?://|www\.", flags=re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_dir(run_id: str) -> Path:
    d = _RUN_STATE_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _strip_fences(text: str) -> str:
    """Remove surrounding ```json ... ``` markdown fences if present."""
    stripped = text.strip()
    # Strip leading ```json or ```
    if stripped.startswith("```"):
        # Remove opening fence line
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1 :]
        # Remove trailing ```
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[: -3].rstrip()
    return stripped.strip()


def _normalize_entity(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def _hangul_ratio(s: str) -> float:
    """Compute Hangul ratio after stripping HTML, URLs, emails.

    Denominator = Hangul + Latin + CJK-other counts.
    Returns 1.0 if denominator is 0 (zero-div guard).
    """
    cleaned = _HTML_TAG_RE.sub("", s)
    cleaned = _URL_RE.sub("", cleaned)
    cleaned = _EMAIL_RE.sub("", cleaned)

    hangul = len(_HANGUL_RE.findall(cleaned))
    latin = len(_LATIN_RE.findall(cleaned))
    cjk_other = len(_CJK_OTHER_RE.findall(cleaned))
    denom = hangul + latin + cjk_other
    if denom == 0:
        return 1.0
    return hangul / denom


def _render_user_template(template_path: Path, **context: Any) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    tmpl = env.get_template(template_path.name)
    return tmpl.render(**context)


def _build_call_a_candidates_context(
    candidates: list[CandidateCluster],
    articles_by_id: dict[str, Article],
) -> list[dict[str, Any]]:
    """Flatten CandidateClusters into the shape the Jinja template expects."""
    out: list[dict[str, Any]] = []
    for c in candidates:
        articles = [articles_by_id[aid] for aid in c.article_ids if aid in articles_by_id]
        out.append(
            {
                "id": c.id,
                "category": c.category,
                "language": c.language,
                "representative_title": c.representative_title,
                "articles": [
                    {
                        "source_name": a.source_name,
                        "language": a.language,
                        "title": a.title,
                        "raw_summary": a.raw_summary or "",
                    }
                    for a in articles
                ],
            }
        )
    return out


def _build_call_b_context(
    key_issues: list[KeyIssue],
    misc: list[KeyIssue],
    today_iso: str,
) -> dict[str, Any]:
    """Assemble the Call B Jinja context from flattened KeyIssues."""
    sections: dict[str, list[dict[str, Any]]] = {}
    for ki in key_issues:
        sections.setdefault(ki.category, []).append(_key_issue_to_context(ki))
    misc_ctx = [_key_issue_to_context(ki) for ki in misc]
    return {"today_iso": today_iso, "sections": sections, "misc": misc_ctx}


def _key_issue_to_context(ki: KeyIssue) -> dict[str, Any]:
    return {
        "cluster_id": ki.cluster_id,
        "canonical_entity_ko": ki.canonical_entity_ko,
        "primary_entity": ki.primary_entity,
        "article_bundle": [
            {
                "source_name": a.source_name,
                "language": a.language,
                "title": a.title,
                "published_at": a.published_at.isoformat(),
                "raw_summary": a.raw_summary or "",
                "enriched_text": a.enriched_text or "",
            }
            for a in ki.article_bundle
        ],
    }


def _extract_usage(response: Any) -> dict[str, int]:
    """Pull a 4-key usage dict from an Anthropic response object."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_creation_input_tokens": int(
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        ),
        "cache_read_input_tokens": int(
            getattr(usage, "cache_read_input_tokens", 0) or 0
        ),
    }


def _response_text(response: Any) -> str:
    """Extract single text block from a response.content list."""
    content = getattr(response, "content", None) or []
    if not content:
        return ""
    block = content[0]
    # anthropic sdk returns TextBlock-like objects with .text
    return getattr(block, "text", "") or ""


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------


class LLMClient:
    """Thin wrapper around anthropic.Anthropic with Call A / Call B helpers.

    Call A uses `call_a_model` (Haiku), Call B uses `call_b_model` (Sonnet).
    Both use ephemeral prompt caching on the system block.
    """

    def __init__(
        self,
        api_key: str,
        call_a_model: str = "claude-haiku-4",
        call_b_model: str = "claude-sonnet-4-6",
        run_dir: Path | None = None,
    ) -> None:
        self.client = anthropic.Anthropic(api_key=api_key)
        self.call_a_model = call_a_model
        self.call_b_model = call_b_model
        self._system_call_a: str | None = None
        self._system_call_b: str | None = None
        self._run_dir = run_dir

    def _load_system_a(self) -> str:
        if self._system_call_a is None:
            self._system_call_a = CALL_A_SYSTEM_PATH.read_text(encoding="utf-8")
        return self._system_call_a

    def _load_system_b(self) -> str:
        if self._system_call_b is None:
            self._system_call_b = CALL_B_SYSTEM_PATH.read_text(encoding="utf-8")
        return self._system_call_b

    # ----- Call A ------------------------------------------------------------

    def call_a(
        self,
        candidates: list[CandidateCluster],
        articles_by_id: dict[str, Article],
    ) -> tuple[CallAResponse, dict[str, int]]:
        """Clustering+canonicalization call.

        Returns (parsed CallAResponse, usage dict).
        On HTTP error: retry once with 5s backoff, else SystemExit(3).
        On schema/coverage error: retry once with feedback, else SystemExit(3).
        """
        system_text = self._load_system_a()
        candidates_ctx = _build_call_a_candidates_context(candidates, articles_by_id)
        user_text = _render_user_template(CALL_A_USER_TEMPLATE, candidates=candidates_ctx)

        input_cluster_ids = {c.id for c in candidates}

        return self._call_a_attempt(
            system_text=system_text,
            user_text=user_text,
            input_cluster_ids=input_cluster_ids,
            retry_left=1,
        )

    def _call_a_attempt(
        self,
        *,
        system_text: str,
        user_text: str,
        input_cluster_ids: set[str],
        retry_left: int,
        feedback: str | None = None,
    ) -> tuple[CallAResponse, dict[str, int]]:
        effective_user = user_text
        if feedback:
            effective_user = f"{user_text}\n\nPREVIOUS ATTEMPT ERROR (fix this):\n{feedback}"

        request = self._build_request(
            model=self.call_a_model,
            system_text=system_text,
            user_text=effective_user,
        )

        # HTTP call with retry
        try:
            response = self.client.messages.create(**request)
        except (anthropic.APIConnectionError, anthropic.APIStatusError, anthropic.RateLimitError) as e:
            if retry_left > 0:
                logger.warning("Call A HTTP error, retrying once in 5s: %s", e)
                time.sleep(5)
                return self._call_a_attempt(
                    system_text=system_text,
                    user_text=user_text,
                    input_cluster_ids=input_cluster_ids,
                    retry_left=retry_left - 1,
                    feedback=feedback,
                )
            self._abort_call_a(raw_text=str(e), tag="call_a_http_abort")

        usage = _extract_usage(response)
        raw_text = _response_text(response)
        stripped = _strip_fences(raw_text)

        # Parse JSON
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as e:
            if retry_left > 0:
                return self._call_a_attempt(
                    system_text=system_text,
                    user_text=user_text,
                    input_cluster_ids=input_cluster_ids,
                    retry_left=retry_left - 1,
                    feedback=f"JSON parse failed: {e}. Raw output:\n{raw_text[:500]}",
                )
            self._abort_call_a(raw_text=raw_text, tag="call_a_schema_abort")

        # Validate schema
        try:
            call_a = CallAResponse.model_validate(parsed)
        except pydantic.ValidationError as e:
            if retry_left > 0:
                return self._call_a_attempt(
                    system_text=system_text,
                    user_text=user_text,
                    input_cluster_ids=input_cluster_ids,
                    retry_left=retry_left - 1,
                    feedback=f"Schema validation failed: {e}",
                )
            self._abort_call_a(raw_text=raw_text, tag="call_a_schema_abort")

        # Coverage check
        output_ids: list[str] = []
        for c in call_a.clusters:
            output_ids.extend(c.input_cluster_ids)
        covered = set(output_ids)
        missing = input_cluster_ids - covered
        duplicates = len(output_ids) != len(covered)
        extra = covered - input_cluster_ids

        if missing or duplicates or extra:
            if retry_left > 0:
                msg = (
                    f"Cluster coverage violation. "
                    f"Missing: {sorted(missing)} | Duplicates: {duplicates} | "
                    f"Unknown: {sorted(extra)}. "
                    f"Every input cluster id must appear in exactly one output cluster."
                )
                return self._call_a_attempt(
                    system_text=system_text,
                    user_text=user_text,
                    input_cluster_ids=input_cluster_ids,
                    retry_left=retry_left - 1,
                    feedback=msg,
                )
            self._abort_call_a(raw_text=raw_text, tag="call_a_schema_abort")

        return call_a, usage

    def _abort_call_a(self, *, raw_text: str, tag: str) -> NoReturn:
        """Persist raw response and SystemExit(3)."""
        if self._run_dir is not None:
            self._run_dir.mkdir(parents=True, exist_ok=True)
            (self._run_dir / "call_a_raw.txt").write_text(raw_text or "", encoding="utf-8")
        logger.error("Call A aborting with tag=%s", tag)
        raise SystemExit(3)

    # ----- Call B ------------------------------------------------------------

    def call_b(
        self,
        key_issues: list[KeyIssue],
        misc: list[KeyIssue] | None = None,
        today_iso: str = "",
    ) -> tuple[LLMBriefing, dict[str, int]]:
        """Write-briefing call.

        Returns (parsed LLMBriefing, usage dict).
        On HTTP error: retry once with 5s backoff, else SystemExit(4).
        On schema/semantic error: retry once with feedback, else SystemExit(4).
        """
        system_text = self._load_system_b()
        ctx = _build_call_b_context(key_issues, misc or [], today_iso)
        user_text = _render_user_template(CALL_B_USER_TEMPLATE, **ctx)

        valid_cluster_ids = {ki.cluster_id for ki in key_issues}
        if misc:
            valid_cluster_ids |= {ki.cluster_id for ki in misc}

        return self._call_b_attempt(
            system_text=system_text,
            user_text=user_text,
            valid_cluster_ids=valid_cluster_ids,
            retry_left=1,
        )

    def _call_b_attempt(
        self,
        *,
        system_text: str,
        user_text: str,
        valid_cluster_ids: set[str],
        retry_left: int,
        feedback: str | None = None,
    ) -> tuple[LLMBriefing, dict[str, int]]:
        effective_user = user_text
        if feedback:
            effective_user = f"{user_text}\n\nPREVIOUS ATTEMPT ERROR (fix this):\n{feedback}"

        request = self._build_request(
            model=self.call_b_model,
            system_text=system_text,
            user_text=effective_user,
        )

        try:
            response = self.client.messages.create(**request)
        except (anthropic.APIConnectionError, anthropic.APIStatusError, anthropic.RateLimitError) as e:
            if retry_left > 0:
                logger.warning("Call B HTTP error, retrying once in 5s: %s", e)
                time.sleep(5)
                return self._call_b_attempt(
                    system_text=system_text,
                    user_text=user_text,
                    valid_cluster_ids=valid_cluster_ids,
                    retry_left=retry_left - 1,
                    feedback=feedback,
                )
            self._abort_call_b(raw_text=str(e), tag="call_b_http_abort")

        usage = _extract_usage(response)
        raw_text = _response_text(response)
        stripped = _strip_fences(raw_text)

        # Parse JSON
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as e:
            if retry_left > 0:
                return self._call_b_attempt(
                    system_text=system_text,
                    user_text=user_text,
                    valid_cluster_ids=valid_cluster_ids,
                    retry_left=retry_left - 1,
                    feedback=f"JSON parse failed: {e}. Raw output:\n{raw_text[:500]}",
                )
            self._abort_call_b(raw_text=raw_text, tag="call_b_schema_abort")

        # Schema validation
        try:
            briefing = LLMBriefing.model_validate(parsed)
        except pydantic.ValidationError as e:
            if retry_left > 0:
                return self._call_b_attempt(
                    system_text=system_text,
                    user_text=user_text,
                    valid_cluster_ids=valid_cluster_ids,
                    retry_left=retry_left - 1,
                    feedback=f"Schema validation failed: {e}",
                )
            self._abort_call_b(raw_text=raw_text, tag="call_b_schema_abort")

        # Semantic validation
        error = _validate_briefing_semantics(briefing, valid_cluster_ids)
        if error is not None:
            if retry_left > 0:
                return self._call_b_attempt(
                    system_text=system_text,
                    user_text=user_text,
                    valid_cluster_ids=valid_cluster_ids,
                    retry_left=retry_left - 1,
                    feedback=f"Semantic validation failed: {error}",
                )
            self._abort_call_b(raw_text=raw_text, tag="call_b_schema_abort")

        return briefing, usage

    def _abort_call_b(self, *, raw_text: str, tag: str) -> NoReturn:
        if self._run_dir is not None:
            self._run_dir.mkdir(parents=True, exist_ok=True)
            (self._run_dir / "call_b_response_raw.json").write_text(
                raw_text or "", encoding="utf-8"
            )
        logger.error("Call B aborting with tag=%s", tag)
        raise SystemExit(4)

    # ----- Request assembly --------------------------------------------------

    def _build_request(self, *, model: str, system_text: str, user_text: str) -> dict[str, Any]:
        """Assemble the request dict with ephemeral cache_control on the system block (AC10a)."""
        return {
            "model": model,
            "max_tokens": 4096,
            "system": [
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": user_text}],
        }


# ---------------------------------------------------------------------------
# Semantic validators (Call B)
# ---------------------------------------------------------------------------


def _validate_briefing_semantics(
    briefing: LLMBriefing,
    valid_cluster_ids: set[str],
) -> str | None:
    """Return error message if semantic validation fails, else None."""
    # cluster_id coverage
    all_items: list[Any] = []
    for items in briefing.sections.values():
        all_items.extend(items)
    if briefing.misc_observations_ko:
        all_items.extend(briefing.misc_observations_ko)

    for item in all_items:
        if item.cluster_id not in valid_cluster_ids:
            return f"cluster_id '{item.cluster_id}' not in input KeyIssue set"

    # Hangul ratio and URL checks on every title/summary
    for item in all_items:
        for field_name, field_val in (
            ("title_ko", item.title_ko),
            ("summary_ko", item.summary_ko),
        ):
            if _URL_TOKEN_RE.search(field_val):
                return f"{field_name} contains a URL token; URLs belong to the renderer"
            ratio = _hangul_ratio(field_val)
            if ratio < _HANGUL_RATIO_MIN:
                return (
                    f"{field_name} Hangul ratio {ratio:.2f} < {_HANGUL_RATIO_MIN}: "
                    f"{field_val[:80]}"
                )

    return None


# ---------------------------------------------------------------------------
# merge_candidate_clusters (R1 sanity checks)
# ---------------------------------------------------------------------------


def merge_candidate_clusters(
    candidates: list[CandidateCluster],
    call_a: CallAResponse,
    articles_by_id: dict[str, Article],
    run_notes: list[str],
    dry_run: bool = False,
) -> list[Cluster]:
    """Fold Call A's merge decisions into authoritative Cluster[].

    Applies R1 sanity checks (category-span ≤ 2, time-span ≤ 72h).
    On reject: unfold into per-candidate Clusters and log to run_notes.
    Scoring fields are placeholder 0.0 — recomputed by rescore_clusters().
    When ``dry_run`` is True, cluster IDs are assigned deterministically as
    ``cluster_0001``, ``cluster_0002``, … in emission order so fixture mocks
    can reference them stably.
    """
    candidates_by_id: dict[str, CandidateCluster] = {c.id: c for c in candidates}
    clusters: list[Cluster] = []
    _counter = 0

    def _new_id() -> str:
        nonlocal _counter
        if dry_run:
            _counter += 1
            return f"cluster_{_counter:04d}"
        return str(uuid.uuid4())

    for idx, ca_out in enumerate(call_a.clusters):
        src_candidates = [candidates_by_id[cid] for cid in ca_out.input_cluster_ids if cid in candidates_by_id]
        if not src_candidates:
            continue

        # Union article ids
        union_article_ids: list[str] = []
        seen: set[str] = set()
        for sc in src_candidates:
            for aid in sc.article_ids:
                if aid not in seen:
                    seen.add(aid)
                    union_article_ids.append(aid)

        merged_articles = [articles_by_id[aid] for aid in union_article_ids if aid in articles_by_id]

        # R1: category-span rule — >2 distinct pre-cluster categories → reject
        pre_categories = {sc.category for sc in src_candidates}
        if len(pre_categories) > _CATEGORY_SPAN_MAX:
            reason = f"category_span_violation idx={idx} categories={sorted(pre_categories)} input_cluster_ids={ca_out.input_cluster_ids}"
            run_notes.append(reason)
            clusters.extend(_unfold_candidates(src_candidates, articles_by_id, _new_id))
            continue

        # R1: time-span rule — published_at max-min > 72h → reject
        if merged_articles:
            published_times = [a.published_at for a in merged_articles]
            span_hours = (max(published_times) - min(published_times)).total_seconds() / 3600.0
            if span_hours > _TIME_SPAN_MAX_HOURS:
                reason = f"time_span_violation idx={idx} span_hours={span_hours:.1f} input_cluster_ids={ca_out.input_cluster_ids}"
                run_notes.append(reason)
                clusters.extend(_unfold_candidates(src_candidates, articles_by_id, _new_id))
                continue

        # Pick primary_entity
        primary_entity = _pick_primary_entity(ca_out.key_entities, merged_articles)

        cluster = Cluster(
            id=_new_id(),
            category=ca_out.category_confirmed,
            canonical_entity_ko=ca_out.canonical_entity_ko,
            primary_entity=primary_entity,
            article_ids=union_article_ids,
            is_cross_lingual_merge=ca_out.is_cross_lingual_merge,
            diffusion_score=0.0,
            novelty_score=0.0,
            combined_score=0.0,
        )
        clusters.append(cluster)

    return clusters


def _pick_primary_entity(
    key_entities: list[str], merged_articles: list[Article]
) -> str:
    """First entry of key_entities preferred; else most frequent extracted_entity."""
    if key_entities:
        return key_entities[0]
    counter: Counter[str] = Counter()
    for art in merged_articles:
        for ent in art.extracted_entities:
            counter[ent] += 1
    if counter:
        return counter.most_common(1)[0][0]
    return ""


def _unfold_candidates(
    src: list[CandidateCluster],
    articles_by_id: dict[str, Article],
    id_factory: Any = None,
) -> list[Cluster]:
    """Split rejected merge back into per-candidate Cluster rows.

    ``id_factory`` (optional callable returning ``str``) lets callers assign
    deterministic IDs when needed; defaults to ``uuid.uuid4()`` for production.
    """
    out: list[Cluster] = []
    for sc in src:
        merged_articles = [articles_by_id[aid] for aid in sc.article_ids if aid in articles_by_id]
        # primary entity from article frequency
        counter: Counter[str] = Counter()
        for art in merged_articles:
            for ent in art.extracted_entities:
                counter[ent] += 1
        primary_entity = counter.most_common(1)[0][0] if counter else ""

        canonical = (sc.representative_title or "")[:60].strip() or "Untitled"

        cid = id_factory() if id_factory is not None else str(uuid.uuid4())
        out.append(
            Cluster(
                id=cid,
                category=sc.category,
                canonical_entity_ko=canonical,
                primary_entity=primary_entity,
                article_ids=list(sc.article_ids),
                is_cross_lingual_merge=False,
                diffusion_score=0.0,
                novelty_score=0.0,
                combined_score=0.0,
            )
        )
    return out


# ---------------------------------------------------------------------------
# rescore_clusters
# ---------------------------------------------------------------------------


def rescore_clusters(
    conn: Any,
    clusters: list[Cluster],
    articles_by_id: dict[str, Article],
    today: datetime,
) -> list[Cluster]:
    """Recompute novelty/diffusion/combined on merged clusters, mutating in place."""
    warmup = is_warmup_phase(conn, today)

    for cluster in clusters:
        cluster_articles = [
            articles_by_id[aid] for aid in cluster.article_ids if aid in articles_by_id
        ]

        # Diffusion
        n_sources = len({a.source_name for a in cluster_articles})
        source_types = {a.source_type for a in cluster_articles}
        source_type_diversity = len(source_types) / 3.0
        diffusion = 0.6 * min(n_sources / 5.0, 1.0) + 0.4 * source_type_diversity

        # Novelty
        prior_days = 0
        if cluster.primary_entity:
            norm = _normalize_entity(cluster.primary_entity)
            prior_days = query_entity_prior_days(conn, norm, today, days=7)
        novelty = max(0.0, 1.0 - 0.15 * prior_days)
        novelty = min(novelty, 1.0)

        # Combined
        if warmup:
            combined = 0.3 * novelty + 0.7 * diffusion
        else:
            combined = 0.55 * novelty + 0.45 * diffusion

        cluster.diffusion_score = diffusion
        cluster.novelty_score = novelty
        cluster.combined_score = combined

    return clusters


# ---------------------------------------------------------------------------
# finalize_sections (Blocker 3)
# ---------------------------------------------------------------------------


def finalize_sections(
    clusters: list[Cluster],
    articles_by_id: dict[str, Article],
    threshold: float = _DEFAULT_SECTION_THRESHOLD,
    max_per_cat: int = _DEFAULT_MAX_PER_CAT,
) -> dict[str, Any]:
    """Group clusters into category sections (threshold-gated) + misc overflow.

    Result:
      {
        "sections": {cat: [KeyIssue, ...], ...},  # only present categories
        "misc":     [KeyIssue, ...]               # ≤ 3 items
      }
    A category section exists iff it has ≥1 cluster meeting threshold.
    Clusters that fail all thresholds flow to misc, sorted by combined desc,
    capped at 3.
    """
    # Group by category
    by_cat: dict[str, list[Cluster]] = {}
    for c in clusters:
        by_cat.setdefault(c.category, []).append(c)

    sections: dict[str, list[KeyIssue]] = {}
    above: list[Cluster] = []
    below: list[Cluster] = []

    for cat, items in by_cat.items():
        items_sorted = sorted(items, key=lambda c: c.combined_score, reverse=True)
        qualified = [c for c in items_sorted if c.combined_score >= threshold]
        taken = qualified[:max_per_cat]
        if taken:
            sections[cat] = [_cluster_to_key_issue(c, articles_by_id) for c in taken]
            above.extend(taken)
        # Unpicked clusters in this category (failed threshold OR overflow past max_per_cat)
        # are candidates for misc.
        taken_ids = {c.id for c in taken}
        for c in items_sorted:
            if c.id not in taken_ids:
                below.append(c)

    # Misc: sorted by combined desc, capped at 3
    below_sorted = sorted(below, key=lambda c: c.combined_score, reverse=True)[:_MISC_CAP]
    misc = [_cluster_to_key_issue(c, articles_by_id) for c in below_sorted]

    return {"sections": sections, "misc": misc}


def _cluster_to_key_issue(
    cluster: Cluster,
    articles_by_id: dict[str, Article],
) -> KeyIssue:
    """Convert a Cluster to a KeyIssue with a bounded article bundle.

    Cap bundle at 5 articles; prefer those with richer enriched_text.
    """
    articles = [articles_by_id[aid] for aid in cluster.article_ids if aid in articles_by_id]
    # Rank: enriched_text length desc (None -> 0), then published_at desc
    articles_ranked = sorted(
        articles,
        key=lambda a: (len(a.enriched_text or ""), a.published_at),
        reverse=True,
    )
    bundle = articles_ranked[:_MAX_ARTICLES_PER_BUNDLE]

    return KeyIssue(
        cluster_id=cluster.id,
        category=cluster.category,
        canonical_entity_ko=cluster.canonical_entity_ko,
        primary_entity=cluster.primary_entity,
        novelty_score=cluster.novelty_score,
        diffusion_score=cluster.diffusion_score,
        combined_score=cluster.combined_score,
        article_bundle=bundle,
        sceep_dimensions=list(cluster.sceep_dimensions),
    )


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def run_summarizer(
    conn: Any,
    scored_candidates: list[tuple[CandidateCluster, float, float, float]],
    articles_by_id: dict[str, Article],
    today: datetime,
    run_id: str,
    dry_run: bool = False,
    api_key: str = "",
    call_a_model: str = "claude-haiku-4",
    call_b_model: str = "claude-sonnet-4-6",
    stage_timings: dict[str, float] | None = None,
) -> tuple[LLMBriefing, list[KeyIssue], list[str], dict[str, Any]]:
    """Full summarizer pipeline: Call A → merge → rescore → finalize → Call B.

    Returns (briefing, key_issues, run_notes, llm_usage).
    """
    run_notes: list[str] = []
    run_dir = _run_dir(run_id)

    candidates = [c for (c, _, _, _) in scored_candidates]

    # ----- Call A -----
    _t_call_a_start = time.time()
    if dry_run:
        mock_path = Path("tests/fixtures/mock_call_a_response.json")
        parsed_a = json.loads(mock_path.read_text(encoding="utf-8"))
        call_a_response = CallAResponse.model_validate(parsed_a)
        call_a_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    else:
        client = LLMClient(
            api_key=api_key,
            call_a_model=call_a_model,
            call_b_model=call_b_model,
            run_dir=run_dir,
        )
        call_a_response, call_a_usage = client.call_a(candidates, articles_by_id)

    _t_call_a_elapsed = time.time() - _t_call_a_start

    # Persist Call A artifacts
    _persist_call_a_artifacts(run_dir, candidates, articles_by_id, call_a_response)

    # ----- Merge + sanity checks -----
    clusters = merge_candidate_clusters(
        candidates, call_a_response, articles_by_id, run_notes, dry_run=dry_run
    )

    # ----- Rescore -----
    clusters = rescore_clusters(conn, clusters, articles_by_id, today)

    # ----- SCTEEP macro tagging (plan v2 PR-3 Task 1) -----
    # Dry-run uses a deterministic keyword-based fallback so sample output
    # shows badges without a live API call; production hits Sonnet via
    # ``tag_macro_clusters``. The call is a no-op when no MacroTrends
    # clusters are present, or when no API key is available.
    from morning_brief.macro_tagger import (
        tag_macro_clusters,
        tag_macro_clusters_dry_run,
    )
    if dry_run:
        clusters = tag_macro_clusters_dry_run(clusters)
    else:
        clusters = tag_macro_clusters(clusters, api_key=api_key)

    # ----- Persist clusters to DB -----
    for cluster in clusters:
        insert_cluster(conn, cluster, run_id)
        insert_cluster_members(conn, cluster.id, cluster.article_ids)

    # ----- Finalize sections -----
    finalized = finalize_sections(clusters, articles_by_id)
    sections_dict: dict[str, list[KeyIssue]] = finalized["sections"]
    misc_issues: list[KeyIssue] = finalized["misc"]

    # Flatten sections for Call B input
    key_issues: list[KeyIssue] = []
    for cat in _CATEGORIES:
        if cat in sections_dict:
            key_issues.extend(sections_dict[cat])

    # ----- Call B -----
    _t_call_b_start = time.time()
    today_iso = today.date().isoformat() if hasattr(today, "date") else str(today)
    if dry_run:
        mock_b_path = Path("tests/fixtures/mock_call_b_response.json")
        parsed_b = json.loads(mock_b_path.read_text(encoding="utf-8"))
        briefing = LLMBriefing.model_validate(parsed_b)
        call_b_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    else:
        briefing, call_b_usage = client.call_b(
            key_issues, misc=misc_issues, today_iso=today_iso
        )

    _t_call_b_elapsed = time.time() - _t_call_b_start

    _persist_call_b_artifacts(run_dir, key_issues, misc_issues, briefing)

    llm_usage = {"call_a": call_a_usage, "call_b": call_b_usage}

    # Populate stage_timings if caller provided one
    if stage_timings is not None:
        stage_timings["call_a"] = _t_call_a_elapsed
        stage_timings["call_b"] = _t_call_b_elapsed

    return briefing, key_issues + misc_issues, run_notes, llm_usage


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _persist_call_a_artifacts(
    run_dir: Path,
    candidates: list[CandidateCluster],
    articles_by_id: dict[str, Article],
    call_a_response: CallAResponse,
) -> None:
    request_payload = {
        "candidates": _build_call_a_candidates_context(candidates, articles_by_id),
    }
    (run_dir / "call_a_request.json").write_text(
        json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "call_a_response.json").write_text(
        call_a_response.model_dump_json(indent=2), encoding="utf-8"
    )


def _persist_call_b_artifacts(
    run_dir: Path,
    key_issues: list[KeyIssue],
    misc: list[KeyIssue],
    briefing: LLMBriefing,
) -> None:
    ki_payload = {
        "key_issues": [ki.model_dump(mode="json") for ki in key_issues],
        "misc": [ki.model_dump(mode="json") for ki in misc],
    }
    (run_dir / "call_b_request.json").write_text(
        json.dumps(ki_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (run_dir / "call_b_response.json").write_text(
        briefing.model_dump_json(indent=2), encoding="utf-8"
    )
    (run_dir / "key_issues.json").write_text(
        json.dumps(ki_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
