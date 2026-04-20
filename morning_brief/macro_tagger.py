"""Dedicated Sonnet pass that labels MacroTab candidates with SCTEEP dimensions.

Plan v2 §D2-D: after Call A clusters land, a small Sonnet call assigns
1–3 SCTEEP dimensions to the ~50 MacroTab candidates (cost guard). The
pass is optional — if ``ANTHROPIC_API_KEY`` is missing or the cluster
list is empty the function returns the input unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable

from morning_brief.models import Cluster, SceepDimension

logger = logging.getLogger(__name__)


# Ordered tuple used for Literal-style membership checks.
_VALID_DIMENSIONS: tuple[str, ...] = (
    "Social",
    "Culture",
    "Technology",
    "Economy",
    "Environment",
    "Politics",
)

MAX_CANDIDATES_PER_RUN = 50

_PROMPT_PATH = Path(__file__).parent.parent / "config" / "macro_prompt.md"


# ---------------------------------------------------------------------------
# Dry-run deterministic fallback (plan v2 PR-3 Task 1)
# ---------------------------------------------------------------------------
#
# When the pipeline runs in ``dry_run`` mode the real Sonnet API is not
# available, yet the generated sample must still surface SCTEEP badges so
# human QA can validate the badge rendering. The fallback assigns 1-3
# dimensions per MacroTab cluster using simple keyword matching on the
# canonical entity + primary entity strings. Production uses the real
# Sonnet pass via :func:`tag_macro_clusters`.

_KEYWORD_TO_DIM: tuple[tuple[tuple[str, ...], SceepDimension], ...] = (
    # Politics — elections, government, regulatory keywords
    (("대선", "election", "선거", "regul", "정부", "parliament", "tariff", "관세", "정책"), "Politics"),
    # Economy — inflation, rates, macro indicators
    (("금리", "inflation", "economy", "경제", "gdp", "recession", "시장"), "Economy"),
    # Technology — AI, semiconductor, tech trends
    (("ai", "기술", "tech", "semiconductor", "반도체", "chip", "로봇", "robot", "software"), "Technology"),
    # Environment — climate, ESG, sustainability
    (("esg", "climate", "환경", "기후", "sustain", "재생", "renewable", "carbon"), "Environment"),
    # Social — demographics, generations, workforce
    (("세대", "gen z", "mz", "고령", "population", "workforce", "여성", "남성", "청년"), "Social"),
    # Culture — media, kpop, entertainment, food trends
    (("k-pop", "kpop", "culture", "문화", "music", "film", "drama", "한류", "food"), "Culture"),
)


def _fallback_dims_for(text: str) -> list[SceepDimension]:
    """Return up to 3 dimensions matched by keyword on ``text``.

    Used exclusively by the dry-run code path so the generated sample shows
    a representative mix of chips without a live API call.
    """
    if not text:
        return []
    lowered = text.lower()
    matched: list[SceepDimension] = []
    for kws, dim in _KEYWORD_TO_DIM:
        for kw in kws:
            if kw in lowered:
                if dim not in matched:
                    matched.append(dim)
                break
        if len(matched) >= 3:
            break
    return matched


def tag_macro_clusters_dry_run(clusters: list[Cluster]) -> list[Cluster]:
    """Dry-run/offline variant of :func:`tag_macro_clusters`.

    Assigns SCTEEP dimensions deterministically via keyword matching on the
    cluster's canonical + primary entity text. MacroTab clusters that fail
    all keyword checks fall back to ``["Social"]`` so at least one chip
    renders — the visible sample must never have a completely empty badge
    row when the dry-run flag is set.
    """
    updated: list[Cluster] = []
    for c in clusters:
        if c.category != "MacroTrends":
            updated.append(c)
            continue
        text = f"{c.canonical_entity_ko} {c.primary_entity}"
        dims = _fallback_dims_for(text)
        if not dims:
            dims = ["Social"]
        updated.append(c.model_copy(update={"sceep_dimensions": dims}))
    return updated


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_payload(clusters: list[Cluster]) -> str:
    """Build the user-message JSON the Sonnet pass consumes."""
    items = [
        {
            "cluster_id": c.id,
            "canonical_entity_ko": c.canonical_entity_ko,
            "primary_entity": c.primary_entity,
            "category": c.category,
        }
        for c in clusters
    ]
    return json.dumps({"clusters": items}, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _parse_response(raw: str) -> dict[str, list[SceepDimension]]:
    """Extract ``{cluster_id: [SceepDimension, ...]}`` from Sonnet raw text.

    Accepts either a top-level ``{"cluster_id": [...], ...}`` mapping or
    a ``{"clusters": [{"cluster_id": ..., "sceep_dimensions": [...]}, ...]}``
    envelope (matches ``config/macro_prompt.md`` example).
    """
    stripped = raw.strip()
    # Strip ```json ... ``` fences if the model wrapped the JSON.
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        last_fence = stripped.rfind("```")
        if first_nl != -1 and last_fence > first_nl:
            stripped = stripped[first_nl + 1 : last_fence].strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(stripped)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    out: dict[str, list[SceepDimension]] = {}
    if isinstance(payload, dict) and "clusters" in payload:
        for entry in payload.get("clusters") or []:
            if not isinstance(entry, dict):
                continue
            cid = entry.get("cluster_id")
            dims = entry.get("sceep_dimensions") or []
            if not isinstance(cid, str) or not isinstance(dims, list):
                continue
            out[cid] = _filter_dims(dims)
    elif isinstance(payload, dict):
        for cid, dims in payload.items():
            if isinstance(cid, str) and isinstance(dims, list):
                out[cid] = _filter_dims(dims)
    return out


def _filter_dims(raw_dims: Iterable[Any]) -> list[SceepDimension]:
    """Keep only valid dims and cap at 3 (plan heuristic #2)."""
    kept: list[SceepDimension] = []
    for d in raw_dims:
        if isinstance(d, str) and d in _VALID_DIMENSIONS and d not in kept:
            kept.append(d)  # type: ignore[arg-type]
        if len(kept) >= 3:
            break
    return kept


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def tag_macro_clusters(
    clusters: list[Cluster],
    *,
    client: Any | None = None,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
) -> list[Cluster]:
    """Tag MacroTab clusters with SCTEEP dimensions.

    Parameters
    ----------
    clusters:
        All candidate clusters (MacroTab + industry). Only clusters whose
        category is ``"MacroTrends"`` are sent to Sonnet.
    client:
        Optional ``anthropic.Anthropic``-compatible client (used by tests
        to inject a mock). When None, a real client is constructed from
        ``api_key`` / ``ANTHROPIC_API_KEY``.
    model:
        Sonnet model id.
    api_key:
        Explicit API key; falls back to ``ANTHROPIC_API_KEY`` env var.

    Returns
    -------
    The same clusters, with ``cluster.sceep_dimensions`` populated for
    MacroTab entries when available. The input is not mutated in place;
    fresh ``Cluster`` instances are returned.

    The function is safe to call without credentials: when neither
    ``client`` nor a usable API key is supplied, the function logs a
    warning and returns the input unchanged.
    """
    macro_clusters = [c for c in clusters if c.category == "MacroTrends"]
    if not macro_clusters:
        return clusters

    # Cost guard: cap at MAX_CANDIDATES_PER_RUN.
    budgeted = macro_clusters[:MAX_CANDIDATES_PER_RUN]
    overflow_ids = {c.id for c in macro_clusters[MAX_CANDIDATES_PER_RUN:]}
    if overflow_ids:
        logger.info(
            "macro_tagger: cost guard dropped %d extra clusters (cap=%d)",
            len(overflow_ids),
            MAX_CANDIDATES_PER_RUN,
        )

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if client is None and not key:
        logger.warning(
            "macro_tagger: no client and no ANTHROPIC_API_KEY; skipping SCTEEP tagging"
        )
        return clusters

    if client is None:
        # Imported here so unit tests that mock away anthropic don't pay
        # the import cost.
        import anthropic

        client = anthropic.Anthropic(api_key=key)

    system_text = _load_prompt()
    user_text = _build_user_payload(budgeted)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_text,
            messages=[{"role": "user", "content": user_text}],
        )
    except Exception as e:  # noqa: BLE001 — defensive, any SDK error
        logger.warning("macro_tagger: Sonnet call failed, skipping tagging: %s", e)
        return clusters

    raw_text = _extract_text(response)
    assignments = _parse_response(raw_text)

    # Return fresh Cluster copies with sceep_dimensions applied.
    updated: list[Cluster] = []
    for c in clusters:
        if c.category == "MacroTrends" and c.id in assignments:
            updated.append(c.model_copy(update={"sceep_dimensions": assignments[c.id]}))
        else:
            updated.append(c)
    return updated


def _extract_text(response: Any) -> str:
    """Pull the text payload out of an anthropic Message response.

    Accepts both real SDK objects and the simple mock stubs used in
    tests (``types.SimpleNamespace`` with ``.content[0].text``).
    """
    if response is None:
        return ""
    content = getattr(response, "content", None)
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)
