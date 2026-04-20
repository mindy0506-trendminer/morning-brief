# Morning Consumer Trend Briefing — Plan v3

**Source spec:** `.omc/specs/deep-interview-morning-consumer-trend-briefing.md` (ambiguity 19.5%, PASSED)
**Supersedes:** `.omc/plans/morning-briefing-plan-v2.md` (ITERATE from Critic: 3 blockers + 6 fixes)
**Plan type:** RALPLAN-DR consensus plan, revision 3
**Target:** Local Python 3.11+ CLI, Windows 11 primary, Git Bash shell
**Scope:** MVP end-to-end vertical slice, 1–2 days of focused work

---

## Changes from v2 (reviewer skim)

1. **AC14 hardened (Blocker 1)** — all LLM response pydantic models now mandate `model_config = ConfigDict(extra="forbid")`. The AC14 test wording changed from "pydantic rejects" to an explicit `ValidationError` assertion on an injected `novelty_score: 0.9` field. Without `extra="forbid"`, pydantic v2's default `extra="ignore"` would silently drop fabricated fields and the test would pass for the wrong reason.
2. **AC15 rewritten (Blocker 2)** — replaced the fragile ratio metric `max(stage)/total < 0.5` with **absolute per-stage hard caps** (collect<180s, select<10s, call_a<45s, call_b<120s, render<5s). The old metric falsely failed on slow-API days even when the run succeeded end-to-end.
3. **1-cluster-category rule pinned (Blocker 3)** — a category section renders **iff** it has ≥1 cluster at threshold. Clusters that fail all categories' thresholds flow into `misc_observations_ko` (cap 3). Dynamic subject line enumerates only rendered sections. §5.4, Step 6, and AC2 all updated to this single rule.
4. **Call A sanity checks added (R1)** — post-Call-A guards in `merge_candidate_clusters()` reject merges that span >2 pre-cluster categories or a >72h `published_at` window, unfold them back to originals, and log to `runs.notes`.
5. **AC8 fixture pair frozen (R2)** — `tests/fixtures/cross_lingual_pair.json` now holds an explicit EN+KO Zara AI-campaign pair; AC8 runs the full dry-run pipeline with a mocked Call A merging them.
6. **Call A failure policy explicit (R3)** — on Call A failure after 1 retry, abort with `SystemExit(3)` and persist raw response. No silent fallback to pre-cluster candidates (which would mask AC8 regressions).
7. **Handoff helper named (R4)** — `summarizer.merge_candidate_clusters(...) -> list[Cluster]` owns the Call-A → scorer transition, including sanity checks and primary-entity selection.
8. **Principles P2 and P4 rewritten (R5)** — P2 now describes the two-call orchestration accurately (single invocation of `morning_brief.py`, not single LLM prompt). P4 softened: cache hits are guaranteed within the 5-minute ephemeral TTL; day-over-day hits are best-effort and not load-bearing for any AC.
9. **Cross-language entity extraction policy explicit (R6)** — both EN and KO extractors run on every article regardless of `article.language`, results union'd, brand-dictionary matches override regex.
10. **Minor polish** — Hangul ratio normalizer pinned (strip HTML tags, `https?://[^\s]+`, `[^\s@]+@[^\s@]+`). AC10b threshold hardened (`cache_read_input_tokens ≥ 500`). AC12 clarified ("<3 feeds each contributed ≥1 article after parsing and filtering"). Template placement picked (sibling `briefing.html.j2`). D5 table gains an embedding-clustering row. `sources.yml` uncertain entries default to "include if accessible on first run, else log and skip."

---

## 1. RALPLAN-DR Summary (revised)

### Principles (5, revised)

1. **Simplicity over automation** — MVP is one `python morning_brief.py` invocation. No scheduler, no daemon, no web UI. Automation is a Phase 2 wrapper. (unchanged from v1/v2)
2. **Pipeline orchestration, not single-prompt collapse** (R5 rewrite) — The LLM pipeline is orchestrated as a **single invocation of `morning_brief.py`**, with distinct **Call A (structure: clustering + canonicalization)** and **Call B (voice: Korean editorial)** separated by a Python-authoritative scoring layer. "One pass" describes the user-facing command, not one LLM call. Each LLM call is inspectable, retryable, and replayable in isolation.
3. **Editorial transparency** — every `KeyIssue` in the draft carries its novelty / diffusion / combined scores as computed by `selector.py` and `summarizer.merge_candidate_clusters()`. The LLM never writes score numbers; the `LLMBriefing` pydantic schema has no numeric score fields and `extra="forbid"` blocks fabricated ones. Scores in the rendered email are bit-exactly reproducible from SQLite state.
4. **Cache-hit-friendly prompt shape** (R5 softened) — Call A and Call B each have a stable system prefix (>1024 tokens). Cache hits are reliable **within the 5-minute ephemeral TTL** (dev iteration, within-run retry on the same prefix). **Day-over-day cache hits are best-effort and not relied on by any AC.** AC10a asserts the `cache_control` directive is always present; AC10b measures server-side hits inside the TTL window only.
5. **Reversible storage** — all intermediate artifacts (raw articles, `entity_history` deltas, candidate clusters, `call_a_response.json`, `call_b_response.json`, `.eml`) are written to disk so any single stage can be re-run without re-fetching. `rerender <run_id>` requires zero API calls.

### Decision Drivers (top 3, unchanged)

1. **Korean output quality** — the user forwards this to Korean-speaking clients; bad Korean = the whole product fails.
2. **Fast time-to-first-valuable-output** — reviewable draft on Day 2 of work, not Day 10.
3. **Low, predictable operating cost** — single laptop, prompt caching mandatory, no per-user infra.

### Viable Options per Key Decision

#### D1. LLM choice — unchanged from v1/v2 (Claude family, swappable)

**Choice: Claude.** Call A = Haiku 4 for speed/cost; Call B = Sonnet 4.6 for Korean fluency. Swappable via `LLM_CALL_A_MODEL` / `LLM_CALL_B_MODEL` env vars. Full alternatives matrix (Sonnet-only vs GPT-4.1 vs Gemini 2.5 Pro) identical to **v1 §1 D1** — not repeated.

#### D2. Email delivery mechanism — unchanged from v1 (.eml file Phase 1)

#### D3. News collection method — unchanged from v1 (RSS-first + targeted OG enrichment)

#### D4. Storage — unchanged from v1 (SQLite at `.omc/state/briefing/briefing.db`)

#### D5. LLM pipeline shape (revised table with embedding-clustering row)

| Option | Pros | Cons |
|---|---|---|
| **Single call (v1 proposal)** | Simpler code; one network round-trip; one prompt to tune | Conflates 5 concerns; `rapidfuzz` cannot merge cross-lingual duplicates (token overlap ~0 between "숏폼 화장품 리뷰" and "short-form beauty reviews"); LLM-written scores drift from Python-computed scores → violates Principle 3. Breaks AC8 by design. |
| **Two-call (chosen)** | Call A (Haiku) handles cross-lingual semantic equivalence trivially; Call A prefix stable → cache-hit-friendly (within 5-min TTL, best-effort day-over-day); Call B (Sonnet) focuses on Korean editorial voice only; each call's failure mode is independently inspectable and retryable; Python scores feed renderer bit-exactly (Principle 3). | Two round-trips (~2–4s extra); two prompts to maintain; two persisted responses. |
| Three-call (cluster → rank → write) | Even more separation of concerns | Overkill for MVP; ranking is deterministic Python math, not LLM work; adds latency without quality gain. |
| **Embedding-based clustering** (instead of Call A) | Multilingual embeddings (e.g. `paraphrase-multilingual-MiniLM-L12-v2` via `sentence-transformers`) handle cross-lingual semantic matching without LLM latency; deterministic; no per-call token cost. | Adds a heavy dep (PyTorch) or a separate embedding API; still needs a separate step for canonical entity label + category confirmation, losing the side-benefit Call A gives for free. Local model startup adds ~3–5s cold-start on every run; API adds another network hop + cost. Not meaningfully cheaper than Haiku Call A at MVP scale (Haiku is ~$0.25/$1.25 per M tokens, the daily briefing input is ~2500 tokens). |

**Choice: Two-call.** Rationale: the spec explicitly names cross-lingual input (한+영 혼합) and repetition/diffusion across sources as acceptance criteria. `rapidfuzz` demonstrably cannot satisfy AC8 for translated duplicates; Haiku can, and produces the canonical Korean label in the same call. Embedding-clustering is a legitimate Phase-2 alternative (FU3) but adds deps and a canonicalization step without saving cost at MVP scale.

**Mild pushback to Architect noted:** v3 keeps Call A = Haiku as default, but if AC8 live-test fails on cross-lingual pairs in practice, the fallback is a one-line config swap to Sonnet. No architectural change. Ring-fenced risk.

### Mode: SHORT (no `--deliberate` flag, no high-risk signal)

MVP scope, single user, no production infra. SHORT mode is appropriate. No pre-mortem or expanded test plan required.

---

## 2. Architecture

### 2.1 Data flow (prose)

```
           ┌──────────────┐
           │ sources.yml  │
           └──────┬───────┘
                  │
         ┌────────▼─────────┐
         │  collector.py    │  feedparser + httpx; OG enrichment on top-N
         │                  │  Entity extraction: BOTH EN+KO extractors on
         │                  │  EVERY article, brand-dict overrides regex
         └────────┬─────────┘
                  │  Article[]  → SQLite.articles
                  │  → ENTITY INGEST: every article's entities logged to
                  │     SQLite.entity_history with first_seen_at
                  ▼
         ┌──────────────────┐
         │  selector.py     │  Python-only pre-clustering (cheap same-lang
         │                  │  dedup via rapidfuzz) + novelty + diffusion
         │                  │  scores → CandidateCluster[]
         └────────┬─────────┘
                  │  CandidateCluster[]
                  ▼
         ┌──────────────────┐
         │  summarizer.py   │  Call A (Haiku): re-cluster across languages
         │                  │    + canonicalize entity + confirm category
         │                  │    → CallAResponse (pydantic, extra=forbid)
         │                  │
         │                  │  merge_candidate_clusters(candidates,
         │                  │    call_a_response) -> list[Cluster]:
         │                  │    - unions article_ids across merged IDs
         │                  │    - picks primary_entity
         │                  │    - SANITY CHECKS: reject merges spanning
         │                  │      >2 pre-cluster categories OR >72h
         │                  │      published_at window → unfold, log
         │                  │
         │                  │  Python recomputes novelty/diffusion on
         │                  │    merged Cluster[] (authoritative)
         │                  │  → picker selects top KeyIssue[]
         │                  │
         │                  │  Call B (Sonnet): write Korean briefing JSON
         │                  │    (no score numbers — only prose + links)
         │                  │    → LLMBriefing (pydantic, extra=forbid)
         └────────┬─────────┘
                  │  LLMBriefing (exec_summary + sections + insight_box)
                  │  + KeyIssue[] with Python scores
                  ▼
         ┌──────────────────┐
         │  renderer.py     │  Jinja2 HTML (sibling briefing.html.j2);
         │                  │  injects {novelty, diffusion, combined} from
         │                  │  Python into each item; builds EmailMessage
         │                  │  → .eml
         └────────┬─────────┘
                  │  out/briefing_YYYY-MM-DD.eml
                  ▼
                (user opens, reviews, sends)
```

### 2.2 File / directory structure (6 code modules)

```
morning_brief/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── morning_brief.py               # CLI entry (argparse): run / dry-run / rerender
├── config/
│   ├── sources.yml
│   ├── categories.yml
│   ├── brands.txt                 # brand dictionary, overrides regex
│   └── editorial.md
├── morning_brief/
│   ├── __init__.py
│   ├── models.py                  # pydantic: Article, Cluster, KeyIssue,
│   │                              # CallAResponse, LLMBriefing, BriefingItem
│   │                              # ALL LLM-response models use
│   │                              # ConfigDict(extra="forbid")
│   ├── db.py                      # SQLite bootstrap + DAO
│   ├── collector.py               # RSS fetch + redirect unwrap + OG enrichment
│   │                              # + EN+KO entity extraction + ingest
│   ├── selector.py                # pre-cluster + novelty + diffusion + picker
│   ├── summarizer.py              # Call A + merge_candidate_clusters + Call B
│   ├── renderer.py                # Jinja2 render + .eml build
│   ├── briefing.html.j2           # sibling template (decision: file, not string)
│   └── prompts/                   # content, not code
│       ├── call_a_system.md       # stable ~1500 tokens — clustering rules
│       ├── call_a_user.j2         # per-run article bundle template
│       ├── call_b_system.md       # stable ~1800 tokens — editorial voice
│       └── call_b_user.j2         # per-run selected cluster bundle template
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── sample_rss.xml
│   │   ├── sample_articles.json
│   │   ├── cross_lingual_pair.json       # AC8 frozen pair (R2)
│   │   ├── mixed_lang_article.json       # R6 EN+KO entity extraction test
│   │   ├── mock_call_a_response.json
│   │   ├── mock_call_a_bad_category_span.json  # R1 sanity test
│   │   ├── mock_call_b_response.json
│   │   └── mock_call_b_fabricated_score.json   # AC14 test
│   ├── test_collector.py
│   ├── test_selector.py
│   ├── test_summarizer.py
│   ├── test_renderer.py
│   └── test_end_to_end_dry_run.py
└── out/                           # .eml files (gitignored)
```

**Count: 6 top-level code modules** (`models`, `db`, `collector`, `selector`, `summarizer`, `renderer`) plus the CLI entry at repo root. Prompts are content files; `briefing.html.j2` is a sibling template file (not a module).

State lives under `.omc/state/briefing/` (`briefing.db`, per-run debug JSON dumps).

### 2.3 Key data schemas (pydantic, revised with extra="forbid")

```python
# morning_brief/models.py  (illustrative — not code to write now)

from pydantic import BaseModel, ConfigDict
from typing import Literal
from datetime import datetime

# -------- Domain models (internal; may permit extras) --------

class Article(BaseModel):
    id: str
    title: str
    source_name: str
    source_type: Literal["TraditionalMedia","SpecializedMedia","CuratedTrendReport"]
    url: str
    canonical_url: str
    language: Literal["ko","en"]
    published_at: datetime   # UTC
    category: str | None
    raw_summary: str
    enriched_text: str | None
    fetched_at: datetime
    extracted_entities: list[str]

class CandidateCluster(BaseModel):
    id: str
    category: str             # pre-cluster category (before Call A)
    article_ids: list[str]
    representative_title: str
    language: Literal["ko","en"]

class Cluster(BaseModel):      # after merge_candidate_clusters() + sanity checks
    id: str
    category: str             # category_confirmed by Call A, post-sanity
    canonical_entity_ko: str
    primary_entity: str       # picked inside merge_candidate_clusters()
    article_ids: list[str]
    is_cross_lingual_merge: bool
    diffusion_score: float
    novelty_score: float
    combined_score: float

class KeyIssue(BaseModel):
    cluster_id: str
    category: str
    canonical_entity_ko: str
    primary_entity: str
    novelty_score: float
    diffusion_score: float
    combined_score: float
    article_bundle: list[Article]   # capped at 5 articles into Call B prompt

# -------- LLM response models (STRICT: extra="forbid") --------

class CallAClusterOut(BaseModel):
    model_config = ConfigDict(extra="forbid")   # Blocker 1
    input_cluster_ids: list[str]
    category_confirmed: Literal["Food","Beauty","Fashion","Living","Hospitality"]
    canonical_entity_ko: str
    is_cross_lingual_merge: bool
    key_entities: list[str]

class CallAResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")   # Blocker 1
    clusters: list[CallAClusterOut]

class BriefingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")   # Blocker 1
    cluster_id: str
    title_ko: str
    summary_ko: str           # 1–3 sentences
    is_paywalled: bool
    # NO score fields — renderer injects from KeyIssue

class LLMBriefing(BaseModel):
    model_config = ConfigDict(extra="forbid")   # Blocker 1
    schema_version: Literal["v2"]
    exec_summary_ko: list[str]           # exactly 3 lines (pydantic validator)
    sections: dict[
        Literal["Food","Beauty","Fashion","Living","Hospitality"],
        list[BriefingItem]
    ]
    misc_observations_ko: list[BriefingItem] | None
    insight_box_ko: str
```

**Why `extra="forbid"` matters (Blocker 1):** pydantic v2's default `extra="ignore"` silently drops unknown fields. Without `extra="forbid"`, an AC14 test that injects a fabricated `novelty_score: 0.9` field would pass for the wrong reason — pydantic would drop the field and the resulting model wouldn't contain it, but the test would have never actually been challenged. With `extra="forbid"`, the same injection raises `ValidationError`, proving the schema structurally rejects score contamination.

---

## 3. Concrete Implementation Steps (ordered, file-level)

### Step 1 — Project scaffold & config

- `pyproject.toml` deps: `feedparser>=6.0`, `httpx>=0.27`, `beautifulsoup4>=4.12`, `pydantic>=2.6`, `jinja2>=3.1`, `pyyaml>=6.0`, `anthropic>=0.40`, `python-dotenv>=1.0`, `rapidfuzz>=3.6`. Dev: `pytest`, `pytest-mock`. **No** `rich`.
- `.env.example`:
  ```
  ANTHROPIC_API_KEY=
  BRIEF_SENDER=Me <me@example.com>
  BRIEF_RECIPIENTS=a@x.com,b@x.com
  LLM_CALL_A_MODEL=claude-haiku-4
  LLM_CALL_B_MODEL=claude-sonnet-4-6
  DRY_RUN=0
  REDACT_RECIPIENTS=0
  ```
- `.gitignore` (verbatim, unchanged from v2):
  ```
  __pycache__/
  *.pyc
  .venv/
  *.egg-info/
  build/
  dist/
  .env
  .env.*
  !.env.example
  out/
  .omc/state/briefing/
  .vscode/
  .idea/
  *.swp
  ```
- `config/categories.yml`, `config/sources.yml`, `config/editorial.md`, `config/brands.txt` — seeded from v1 §6. **Uncertain feeds policy (polish item):** any feed URL in `sources.yml` flagged with `status: uncertain` is included if it returns HTTP 2xx on first run; on any error (DNS, 4xx, 5xx, parse failure) the collector logs the failure to `runs.notes` and skips the feed for that run. No researcher verification blocks the MVP.
- **PII note** in README: `out/*.eml` contains recipient email addresses; set `REDACT_RECIPIENTS=1` to replace the `To:` header with `__REDACTED__`.
- **Depends on:** nothing.

### Step 2 — Data layer

- `morning_brief/models.py` — pydantic models from §2.3, with **`ConfigDict(extra="forbid")` on every LLM-response model** (`CallAClusterOut`, `CallAResponse`, `BriefingItem`, `LLMBriefing`).
- `morning_brief/db.py` — SQLite schema, idempotent `bootstrap()`. Tables:
  - `articles` (id, canonical_url, title, source_name, source_type, lang, category, published_at, raw_summary, enriched_text, fetched_at)
  - `entity_history` (entity_text, entity_norm, first_seen_at, last_seen_at, total_occurrences, article_ids_json) — **populated from every collected article** (not just selected KeyIssues)
  - `clusters` (id, category, canonical_entity_ko, primary_entity, is_cross_lingual_merge, novelty_score, diffusion_score, combined_score, created_at)
  - `cluster_members` (cluster_id, article_id)
  - `runs` (id, started_at, completed_at, run_duration_seconds, stage_durations_json, llm_usage_json, schema_version, notes)
- **Depends on:** Step 1.
- **Acceptance:** unit test instantiates each LLM-response pydantic model with an extra field (`novelty_score: 0.9`) and asserts `ValidationError` is raised (preview of AC14).

### Step 3 — Collector (with cross-language entity ingest) — R6 applied

- `morning_brief/collector.py`:
  - Iterate `sources.yml`, fetch via `httpx` (timeout 8s, 3 retries, 1 req/s per host), parse with `feedparser`.
  - **Google News RSS redirect unwrap:** after fetching, if `link` is `news.google.com/rss/articles/...`, follow with a HEAD request (or lightweight GET + `<meta http-equiv="refresh">` parse) and store the publisher's canonical URL in `Article.canonical_url`. Fall back to the google link if unwrap fails.
  - Within-run dedup by `canonical_url`.
  - Category assignment: source metadata first; fallback keyword match on title+summary using `config/categories.yml`.
  - **Enrichment** (top-N by recency, N=40): fetch HTML, parse `<meta property="og:description">` and first `<p>`. Skip if paywall markers detected.
  - **Entity extraction (R6 — cross-language policy, explicit):**
    - **Run BOTH extractors on every article, regardless of `article.language`.**
    - English extractor: regex `[A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]+){0,3}`.
    - Korean extractor: strip expanded postposition list — `은/는/이/가/을/를/의/에/와/과/로/으로/에서/부터/까지/보다/처럼/만/도` — then match (a) brand tokens from `config/brands.txt` and (b) sequences of 2+ Hangul chars preceded by quotes or followed by `은/는/이/가`.
    - **Merge:** `entities = set(english_matches | korean_matches)`.
    - **Brand dictionary override:** if `config/brands.txt` maps `자라 → Zara`, the canonical `Zara` replaces the raw match; the override applies to results from both extractors.
    - Normalize to lowercase + NFC before storing.
  - **Entity ingest** (every article, not just future-selected KeyIssues): upsert each extracted entity into `entity_history`. New `entity_norm` → set `first_seen_at = today`; existing → update `last_seen_at`, increment `total_occurrences`.
- **Depends on:** Step 2.
- **Acceptance:**
  - Fixture RSS → ≥5 `Article` with correct categories AND `entity_history` populated from every article.
  - Google News fixture with redirect URL → `canonical_url` differs from `url`.
  - **R6 test:** article with body `'Samsung Galaxy S26가 한국에 출시됐다'` extracts `Samsung` and `Galaxy` (EN regex), and — if `한국` is in `brands.txt` — extracts it too. If `한국` is not in `brands.txt`, the Korean extractor skips it (no bare common-noun capture). Brand-dictionary entry `자라 → Zara` test: a Korean-body article mentioning `자라` yields canonical `Zara`.

### Step 4 — Selector (pre-cluster + score + pick)

- `morning_brief/selector.py`:
  - **Same-language pre-cluster** via `rapidfuzz.fuzz.token_set_ratio ≥ 75` on normalized titles, single-linkage within category + 72h window. Produces `CandidateCluster[]`.
  - **Scoring on candidate clusters** (will be recomputed post-Call-A on merged `Cluster[]`):
    - `diffusion_score = 0.6 * min(n_sources / 5, 1.0) + 0.4 * source_type_diversity`
    - `novelty_score = max(0, 1 - 0.15 * prior_day_hits_last_7d)` where `prior_day_hits_last_7d` counts days in the last 7 where the primary entity appeared in `entity_history`.
    - **Warmup rule:** if `min(entity_history.first_seen_at) > today - 7d` for the DB as a whole → `combined = 0.3 * novelty + 0.7 * diffusion`. Else → `combined = 0.55 * novelty + 0.45 * diffusion`.
    - **Day-1 behavior:** on the first run, warmup weighting forces diffusion-led selection (every entity is "new", so novelty=1.0 for all; diffusion is the discriminator). Documented.
  - **Picker:** top-N per category (`MIN_PER_CAT=2`, `MAX_PER_CAT=3`), global cap 13. **Per Blocker 3, picker output is pre-Call-A; final section-vs-misc placement happens in `summarizer.finalize_sections()` after merge_candidate_clusters() completes.**
- **Depends on:** Step 3.
- **Acceptance:**
  - Synthetic test: 2 same-lang near-dupes merge; different-lang pair is left unmerged at this stage.
  - `test_selector_novelty_warmup` asserts the 7-day warmup weight shift activates when `entity_history` has <7 days of data.

### Step 5 — Summarizer (two-call pipeline with explicit handoff + sanity checks)

- `morning_brief/summarizer.py` orchestrates both calls and owns `merge_candidate_clusters()`. `morning_brief/prompts/` holds stable prompt content.

#### 5a. Call A — Cluster + Canonicalize (Haiku)

**System prefix (~1500 tokens, `prompts/call_a_system.md`, `cache_control: ephemeral`):**
```
ROLE: You are a Korean-fluent clustering editor for a consumer-trend briefing.

TASK: Given N candidate article clusters (already pre-grouped by same-language
title similarity), decide which clusters actually describe THE SAME UNDERLYING
STORY or TREND across languages, and emit a canonical Korean label for each
merged group.

CLUSTERING RULES:
 - Merge across languages when the core entity, event, or trend is
   semantically equivalent. Example: "Zara launches AI-generated campaign"
   and "자라, AI 생성 캠페인 공개" → same story.
 - Merge across sources when the trend label is equivalent, even if angles
   differ. Example: "short-form beauty reviews on YouTube" and
   "숏폼 화장품 리뷰" → same trend.
 - DO NOT merge when the only overlap is a category or a shared brand
   mentioned incidentally.

CANONICALIZATION:
 - canonical_entity_ko: a 2–6 word Korean noun phrase naming the story/trend.
 - category_confirmed: pick exactly one of Food / Beauty / Fashion / Living /
   Hospitality. If ambiguous, pick the dominant one.
 - is_cross_lingual_merge: true if the merged input cluster ids include
   both ko-language and en-language candidate clusters.

5 CATEGORY DEFINITIONS:
 (Food / Beauty / Fashion / Living / Hospitality — ~80 tokens each)

ENTITY EXTRACTION:
 - Return up to 3 key entities per cluster (brand, product line, technology,
   behavior pattern).

OUTPUT CONTRACT:
 - Respond with JSON matching exactly:
   { "clusters": [
     { "input_cluster_ids": [...],
       "category_confirmed": "...",
       "canonical_entity_ko": "...",
       "is_cross_lingual_merge": bool,
       "key_entities": [...] } ] }
 - Every input cluster_id appears in EXACTLY ONE output cluster.
 - No commentary outside the JSON.
 - No numeric scores anywhere. The Python scoring layer owns those values.

FEW-SHOT: 2 examples (one cross-lingual merge, one correct non-merge).
```

**User payload (per-run, `prompts/call_a_user.j2`):** titles + raw_summary + source + lang only for each candidate cluster — NO article bodies.

**Response handling:**
- Parse response JSON → validate against `CallAResponse` (pydantic with `extra="forbid"`).
- If `input_cluster_ids` coverage is incomplete or duplicated → structured retry with targeted error message. One retry only.
- **Call A failure policy (R3, explicit):**
  - **HTTP error** (connection / 5xx / rate-limit): retry once with 5s backoff. On second failure → **abort with `SystemExit(3)` and persist the raw response to `.omc/state/briefing/runs/<run_id>/call_a_raw.txt`**. Do NOT fall back to pre-cluster candidates — that would silently skip cross-lingual merging and produce a stealth AC8 regression.
  - **JSON/schema error** (malformed JSON, pydantic `ValidationError`, coverage violation): retry once with structured feedback (the pydantic error message appended to the user prompt). On second failure → same abort path, `SystemExit(3)` + persist raw response.
  - Log abort reason to `runs.notes` with one of: `call_a_http_abort`, `call_a_schema_abort`.

#### 5b. merge_candidate_clusters() — named handoff helper (R4)

```python
# morning_brief/summarizer.py (signature, illustrative)

def merge_candidate_clusters(
    candidates: list[CandidateCluster],
    call_a: CallAResponse,
) -> list[Cluster]:
    """
    Convert Call A's cluster-membership decisions into the authoritative
    Cluster[] that the scorer consumes.

    Responsibilities:
    1. Union `article_ids` across each merged group of `input_cluster_ids`.
    2. Pick `primary_entity`:
       - First entry of `CallAClusterOut.key_entities` is preferred.
       - Fallback: the entity with the highest frequency across the union
         of `extracted_entities` on all merged articles.
    3. Apply R1 sanity checks BEFORE returning (see below).
    4. Attach category_confirmed, canonical_entity_ko, is_cross_lingual_merge
       from Call A's output.

    Returns the Cluster[] that feeds directly into the Python scoring step
    and the picker.
    """
```

**R1 sanity checks (post-Call-A, pre-scoring, inside `merge_candidate_clusters`):**
- **Category-span rule:** reject a merge if the union of its `article_ids` spans >2 distinct pre-cluster `CandidateCluster.category` values. (Two categories is tolerated because cross-category trend stories exist — e.g. an Athleisure-type story may legitimately span Fashion and Living. Three or more is a signal of incorrect merging.)
- **Time-span rule:** reject a merge if the union's `published_at` span (max − min) exceeds 72 hours.
- **On reject:** unfold the merge — split back into the original pre-cluster `CandidateCluster` entries (each becomes its own `Cluster` with `is_cross_lingual_merge=False`, `canonical_entity_ko` defaulting to the `representative_title` truncated/stripped). Log one entry to `runs.notes` per rejected merge with reason `category_span_violation` or `time_span_violation` and the offending Call-A cluster's index.
- These rejections are **non-fatal** (unlike R3's LLM failure aborts). The run continues with the unfolded clusters.

#### 5c. Python scoring on merged Cluster[]

After `merge_candidate_clusters()` returns, the selector's novelty/diffusion logic runs again on the merged `Cluster[]`:
- `n_sources` and `source_type_diversity` are computed on the union of articles across merged candidates.
- `primary_entity` (picked inside `merge_candidate_clusters`) drives the novelty lookup.
- Warmup rule unchanged.

Final `combined_score` on each `Cluster` is the authoritative score threaded to `KeyIssue` → renderer.

#### 5d. Picker → finalize_sections() (Blocker 3 single rule)

After scoring, `summarizer.finalize_sections(clusters: list[Cluster]) -> dict`:
- Sort clusters per category by `combined_score` desc.
- Take up to `MAX_PER_CAT=3` per category; **a category section exists iff it has ≥1 cluster at threshold**.
- Clusters that fail all categories' thresholds (e.g. threshold is `combined_score ≥ 0.35`; configurable) flow into `misc_observations_ko`, capped at 3 items total.
- Result shape:
  ```python
  {
      "sections": { "Food": [KeyIssue, ...], "Beauty": [...], ... },  # omitted-if-empty
      "misc": [KeyIssue, ...]  # ≤3 items, or [] if nothing qualifies
  }
  ```
- **Categories with 0 clusters are absent from `sections` entirely** — not rendered as empty sections, not placeholder'd. The dynamic subject line enumerates only the keys present in `sections` (plus "기타 관찰" if `misc` is non-empty).

#### 5e. Call B — Write Briefing (Sonnet)

**System prefix (~1800 tokens, `prompts/call_b_system.md`, `cache_control: ephemeral`):**
```
ROLE: You are a Korean consumer-trend editor writing a morning briefing for
1–3 Korean-speaking executives.

EDITORIAL VOICE:
 - Plain, crisp Korean. No "이 기사는…" padding.
 - Prefer 체언 중심 문장; avoid 영어 음차 when a natural Korean term exists
   (e.g. "숏폼 리뷰", not "쇼트폼 review").
 - 3-line exec summary: each line ≤ 60 Korean characters, one trend each.
 - Each item summary: 1–3 sentences, ≤ 200 Korean characters.
 - insight_box: 2–4 sentences, trend synthesis across sections.

SCORE POLICY: Do NOT write any numeric score. Score columns are handled
by the renderer from Python-computed values. Focus on prose quality.

OUTPUT SCHEMA (strict, pydantic-validated with extra=forbid):
 { "schema_version": "v2",
   "exec_summary_ko": [str, str, str],
   "sections": { <subset of Food/Beauty/Fashion/Living/Hospitality>:
                 [BriefingItem, ...] },
   "misc_observations_ko": [BriefingItem] | null,
   "insight_box_ko": str }
 BriefingItem = { "cluster_id": str, "title_ko": str,
                  "summary_ko": str, "is_paywalled": bool }
 - cluster_id MUST match one of the input KeyIssue cluster_ids exactly.
 - title_ko / summary_ko MUST be Korean (>=80% Hangul after URL+email
   stripping; see renderer spec).
 - OMIT a category key entirely if its KeyIssue list is empty
   (do not emit an empty array).
 - Source URLs are NOT in your output; renderer joins them from KeyIssue.

FORBIDDEN:
 - Inventing source_url fields.
 - Changing cluster_id or inventing new clusters.
 - Numeric scores anywhere (any numeric field WILL be rejected by the
   schema's extra="forbid").
 - Emojis in the body.

FEW-SHOT: 1 complete good briefing (~600 tokens) + 1 bad briefing with
annotated problems.
```

**User payload (`prompts/call_b_user.j2`):** selected `KeyIssue[]` with category, canonical_entity_ko, and full article bundles (title, source_name, lang, published_at, raw_summary, enriched_text, canonical_url, is_paywalled). **No score numbers in user payload** — renderer injects them.

**Response handling:**
- pydantic validation against `LLMBriefing` (with `extra="forbid"`):
  - `exec_summary_ko` length exactly 3 (pydantic validator).
  - Every `cluster_id` in any `BriefingItem` exists in the input `KeyIssue` set (semantic validator).
  - Body Hangul ratio ≥ 80% (see polish note below for exact normalizer).
  - No `http`/`www.` tokens in `summary_ko` / `title_ko` (those belong in renderer).
  - Unknown fields (e.g. fabricated `novelty_score`) → `ValidationError`.
- **On validation failure:** one structured retry with the specific pydantic error appended to the user prompt. If retry also fails, abort with `SystemExit(4)` and persist raw response to `.omc/state/briefing/runs/<run_id>/call_b_response_raw.json`.

**Hangul ratio normalizer (polish):** before counting Hangul ratio on `title_ko` / `summary_ko`, strip:
1. HTML tags: `<[^>]+>`
2. URLs: `https?://[^\s]+`
3. Email addresses: `[^\s@]+@[^\s@]+`

Then count `Hangul chars / (Hangul + Latin + CJK-other)`. Ratio must be ≥ 0.80. Proper nouns rendered in Latin (e.g. "Zara") do not count against the ratio because Latin is part of the denominator, but the 20% Latin allowance accommodates them.

**Caching:** both Call A and Call B use `cache_control: {"type":"ephemeral"}` on the system block. AC10a asserts this unconditionally on the request dict.

**Persisted artifacts per run** (`.omc/state/briefing/runs/<run_id>/`):
- `call_a_request.json`, `call_a_response.json` (or `call_a_raw.txt` on abort), `schema_version: "v2"`.
- `call_b_request.json`, `call_b_response.json` (or `call_b_response_raw.json` on abort), `schema_version: "v2"`.
- `key_issues.json` — the `KeyIssue[]` snapshot used by renderer and `rerender`.

**DRY_RUN=1:** skips both network calls; loads `tests/fixtures/mock_call_a_response.json` and `mock_call_b_response.json`.

- **Depends on:** Step 4.
- **Acceptance:**
  - Call A fixture test: 2 input candidate clusters with cross-lingual-equivalent titles merge; unrelated clusters don't.
  - **R1 sanity test:** `mock_call_a_bad_category_span.json` merges one article from `food` with one from `beauty` (via `input_cluster_ids` spanning both). `merge_candidate_clusters()` unfolds them back to separate clusters and logs `category_span_violation` to `runs.notes`. Asserted in `test_summarizer.py`.
  - Call A HTTP abort test: mock the Anthropic client to raise a connection error twice → assert `SystemExit(3)` and `call_a_raw.txt` exists.
  - Call B pydantic validation test: fabricated `cluster_id` → retry triggered with targeted error message. If retry also bad → `SystemExit(4)`.
  - **AC14 test** (preview, full form in §7): `mock_call_b_fabricated_score.json` injects `novelty_score: 0.9` into one `BriefingItem`. Loading via `LLMBriefing.model_validate(...)` raises `pydantic.ValidationError` (not `ValueError`, not silent drop).
  - DRY_RUN path produces a valid `LLMBriefing` from fixtures with zero API calls.

### Step 6 — Renderer (Blocker 3 rule + score injection)

- `morning_brief/renderer.py`:
  - Joins `LLMBriefing.sections[*]` items by `cluster_id` with the full `KeyIssue[]` list (Python-computed scores + source URL list).
  - **Jinja2 template placement (polish decision):** sibling file `morning_brief/briefing.html.j2`. Not an inline string constant. Renderer loads via `jinja2.Environment(loader=FileSystemLoader(Path(__file__).parent))`.
  - Each item renders: `title_ko`, `summary_ko`, score pills (e.g. `신규성 0.82 · 확산도 0.71 · 종합 0.74`), source link list (max 3 canonical URLs joined from `KeyIssue.article_bundle`), `[요약본]` tag if `is_paywalled`.
  - **Section rendering rule (Blocker 3, pinned):**
    - Iterate a fixed category order `[Food, Beauty, Fashion, Living, Hospitality]`.
    - Render a `<section>` **iff** `LLMBriefing.sections.get(category)` is present AND non-empty.
    - Missing or empty category keys are silently skipped (no placeholder).
    - If `LLMBriefing.misc_observations_ko` is non-empty, render a final `<section>` titled "기타 관찰" with those items (no score pills — just `title_ko` + `summary_ko` + source link).
  - **Dynamic subject line (Blocker 3 consistent):**
    - Build from the category keys that rendered a section, in canonical order.
    - Append " · 기타 관찰" iff the misc section rendered.
    - Example: Food, Beauty, Living rendered + misc non-empty → `"[소비재 트렌드 조간] 2026-04-18 (Food/Beauty/Living · 기타 관찰)"`.
    - Never list an empty or omitted section.
  - Builds `EmailMessage` (multipart/alternative plain + HTML) → writes `out/briefing_YYYY-MM-DD.eml`.
  - **PII redaction:** if `REDACT_RECIPIENTS=1`, write `To: __REDACTED__` and omit recipient addresses from the body footer.
  - Prints absolute output path to stdout via stdlib `print` (no `rich`).
- **Depends on:** Step 5.
- **Acceptance:**
  - Rendered HTML shows Python-computed scores, not LLM numbers.
  - Subject line matches the Blocker-3 join rule on a fixture that has Fashion empty and misc non-empty.
  - 1-cluster-category test: fixture where `LLMBriefing.sections["Food"]` has exactly 1 item → Food section renders with 1 item (NOT pushed to misc). Fixture where `LLMBriefing.sections` does not contain `"Fashion"` at all → no Fashion section rendered, subject line omits Fashion.
  - `.eml` opens cleanly in Outlook/Thunderbird/Apple Mail.

### Step 7 — CLI + end-to-end wiring

- `morning_brief.py` at repo root — argparse subcommands:
  - `run` — full pipeline.
  - `dry-run` — `DRY_RUN=1`, mocked both LLM calls.
  - `rerender <run_id>` — re-runs renderer from persisted `call_b_response.json` + `key_issues.json`; zero API calls.
  - `--limit-per-cat N` override.
- Per-run debug artifacts: `.omc/state/briefing/runs/<YYYY-MM-DD-HHMM>/` with all JSON dumps + the final `.eml`.
- `stage_durations_json` populated for every run: `{collect, select, call_a, call_b, render}` in seconds, float.
- **Depends on:** Step 6.
- **Acceptance:**
  - `python morning_brief.py dry-run` exits 0 in <30s on fixtures with zero network calls.
  - `runs.stage_durations_json` has all 5 stages populated.

### Step 8 — Tests + smoke validation (with frozen AC8 fixture)

- `tests/test_collector.py` — RSS parse + Google News redirect unwrap + R6 cross-language entity extraction + entity ingest on every article.
- `tests/test_selector.py` — pre-clustering, novelty warmup, scoring, picker.
- `tests/test_summarizer.py` — prompt assembly, pydantic validation (including `extra="forbid"` for all 4 LLM-response models), retry path, cache_control presence, **R1 sanity checks** (category-span + time-span unfold), **R3 abort paths**.
- `tests/test_renderer.py` — dynamic subject line per Blocker 3, score injection, PII redaction mode, 1-cluster-category section.
- `tests/test_end_to_end_dry_run.py` — full pipeline on fixtures; asserts all automatable ACs.
- **AC8 frozen fixture (R2):** `tests/fixtures/cross_lingual_pair.json`:
  ```json
  [
    {
      "id": "en_zara_001",
      "title": "Zara launches AI-generated campaign featuring synthetic models",
      "source_name": "Business of Fashion",
      "source_type": "SpecializedMedia",
      "url": "https://www.businessoffashion.com/news/retail/zara-ai-campaign/",
      "canonical_url": "https://www.businessoffashion.com/news/retail/zara-ai-campaign/",
      "language": "en",
      "published_at": "2026-04-17T14:00:00Z",
      "category": "Fashion",
      "raw_summary": "Spanish fast-fashion retailer Zara unveiled its first wholly AI-generated marketing campaign this week, featuring synthetic models created via diffusion-based tooling."
    },
    {
      "id": "ko_zara_001",
      "title": "자라, AI 생성 캠페인 공개…합성 모델 등장",
      "source_name": "패션비즈",
      "source_type": "TraditionalMedia",
      "url": "https://www.fashionbiz.co.kr/article/zara-ai-campaign.html",
      "canonical_url": "https://www.fashionbiz.co.kr/article/zara-ai-campaign.html",
      "language": "ko",
      "published_at": "2026-04-17T15:30:00Z",
      "category": "Fashion",
      "raw_summary": "스페인 패스트패션 브랜드 자라가 AI로 생성한 합성 모델을 활용한 첫 마케팅 캠페인을 공개했다."
    }
  ]
  ```
- **AC8 test procedure** (replaces v2's "live smoke test on one real pair"):
  1. Load the fixture pair into the collector path.
  2. Run the full `DRY_RUN=1` pipeline.
  3. Mock `mock_call_a_response.json` such that Call A returns one merged output cluster whose `input_cluster_ids` includes both candidate cluster IDs.
  4. Assert the final rendered `.eml` contains **exactly 1 cluster with both source URLs**, not 2 separate items.
  5. Assert `Cluster.is_cross_lingual_merge == True` on the persisted `clusters` row.
- README with Windows/Git Bash setup: `python -m venv .venv && source .venv/Scripts/activate && pip install -e . && cp .env.example .env && python morning_brief.py dry-run && python morning_brief.py run`.
- **Depends on:** Step 7.
- **Acceptance:** `pytest` runs green locally with zero network calls.

---

## 4. Prompt Engineering

Summary of shape (detail in Step 5):

| Call | Model | System prefix | User payload | Cached? | Output |
|---|---|---|---|---|---|
| A | Haiku 4 | ~1500 tokens (clustering rules + category defs + entity extraction + 2 few-shots) | Candidate clusters: titles + raw_summary + source + lang only | Yes (`ephemeral`) | `CallAResponse` (JSON, `extra="forbid"`) |
| B | Sonnet 4.6 | ~1800 tokens (editorial voice + output schema + 1 good + 1 bad few-shot) | Selected KeyIssues with full article bundles (no scores) | Yes (`ephemeral`) | `LLMBriefing` (JSON, `extra="forbid"`, no scores, no URLs) |

Both prefixes clear the 1024-token minimum for Anthropic ephemeral caching with comfortable margin. **Cache semantics (revised):** within the 5-minute ephemeral TTL, the second-and-later requests on the same prefix reliably hit the cache (AC10b). Day-over-day cache hits are best-effort — the ephemeral TTL is 5 minutes, so a daily run at ~07:00 KST the next day will not hit yesterday's cache. The only real-world day-over-day cache benefit is from within-run retries and dev iteration. No AC depends on day-over-day caching.

---

## 5. Selection / Ranking Logic (revised)

### 5.1 Pre-clustering (Python, same-language only)

Token-overlap single-linkage as in v1 §5.1, threshold 75, 72h window, per category. Only same-language within a candidate cluster. Brand-overlap safety net for Fashion/Beauty unchanged.

### 5.2 Cross-language clustering (Call A + sanity checks)

Delegated to Haiku. Python's `rapidfuzz` cannot bridge "숏폼 화장품 리뷰" ≈ "short-form beauty reviews"; Haiku does this. Output is accepted **with R1 sanity checks as a guardrail**: merges spanning >2 pre-cluster categories or >72h `published_at` are unfolded back to originals inside `merge_candidate_clusters()`. These rejections are logged but non-fatal.

### 5.3 Scoring (Python, post Call A, post sanity checks)

Recomputed on merged clusters returned by `merge_candidate_clusters()`:

- `diffusion_score = 0.6 * min(n_sources / 5, 1.0) + 0.4 * source_type_diversity`
- `novelty_score = max(0, 1 - 0.15 * prior_day_hits_last_7d)` where `prior_day_hits_last_7d` counts days in the last 7 where `primary_entity` appeared in `entity_history`.
- **Warmup rule:** if `min(entity_history.first_seen_at) > today - 7d` for the DB overall → `combined = 0.3 * novelty + 0.7 * diffusion`. Else → `combined = 0.55 * novelty + 0.45 * diffusion`.
- **Day-1 behavior:** warmup weighting forces diffusion-led selection. Documented.

### 5.4 Picking (Blocker 3 single rule)

**Rule (pinned):**
> A category section renders if and only if it has ≥1 cluster at threshold. Categories with 0 clusters are omitted from the sections list entirely. Clusters that fail all categories' thresholds flow into `misc_observations_ko` (capped at 3). The dynamic subject line lists only categories that rendered a section.

Flow:
1. Sort `Cluster[]` per category by `combined_score` desc.
2. For each category, take up to `MAX_PER_CAT=3` clusters whose `combined_score ≥ 0.35` (configurable threshold).
3. If a category has zero qualifying clusters, that category key is **absent** from `LLMBriefing.sections` — no empty list, no placeholder.
4. Any cluster that did not make its category's top-3-at-threshold is a candidate for misc; take the top 3 by `combined_score` across all such remnants → `misc_observations_ko` (or `null`/`[]` if empty).
5. Global cap: 13 items across sections + misc.

**OQ4 resolved in v2 and unchanged in v3:** slow-news-day categories that produce zero clusters at threshold are simply absent. A category with exactly 1 cluster at threshold **does render its own section with 1 item** (not pushed to misc).

---

## 6. News Source List

**Unchanged from v1 §6.** Full YAML list reproduced there; v3 does not duplicate. Two adds (`foodnavigator.com/rss`, `cosmeticsbusiness.com/rss`) are flagged `status: uncertain` and handled per Step 1's policy: included if accessible on first run, else logged to `runs.notes` and skipped. No researcher verification blocks the MVP. Google News RSS query pattern identical. Redirect unwrap added per Step 3.

---

## 7. Testable Acceptance Criteria (revised, ≥15 items)

| # | Criterion | Verification |
|---|---|---|
| AC1 | `python morning_brief.py dry-run` exits 0 in <30s on fixtures with zero network calls | CI: `DRY_RUN=1 pytest tests/test_end_to_end_dry_run.py -q` |
| AC2 | `.eml` renders a `<section>` **iff** `LLMBriefing.sections[category]` is present and non-empty; missing categories are absent (no placeholder). `기타 관찰` section renders iff `misc_observations_ko` is non-empty. Subject line enumerates only rendered sections. | `test_renderer.py` with fixture missing Fashion + misc present; parse `.eml`, assert no Fashion `<section>`, assert subject line excludes Fashion |
| AC3 | `exec_summary_ko` has exactly 3 lines; `insight_box_ko` non-empty | pydantic-enforced; e2e test asserts `len==3` |
| AC4 | Each rendered category section has 1–3 items (Blocker 3: 1 is legal); total items across sections + misc ≤ 13 | Unit test on `finalize_sections()`; e2e test asserts rendered item count |
| AC5 | Every item has ≥1 source URL as clickable link in the HTML body | Parse `.eml`, assert `<a href="http` count ≥ item count |
| AC6 | Body text Hangul ratio ≥ 80% after stripping HTML tags (`<[^>]+>`), URLs (`https?://[^\s]+`), and emails (`[^\s@]+@[^\s@]+`) | `test_renderer.py` Unicode ratio check with the explicit normalizer |
| AC7 | Live run completes in <10 minutes end-to-end | `runs.run_duration_seconds < 600` |
| AC8 | Cross-lingual near-duplicate titles end up in the SAME final cluster. **Fixture: `tests/fixtures/cross_lingual_pair.json` (Zara EN+KO pair, R2).** Run full DRY_RUN pipeline with mocked Call A merging both; assert `.eml` contains exactly 1 cluster with both source URLs | `test_end_to_end_dry_run.py::test_ac8_cross_lingual_merge` |
| AC9 | A story whose primary entity appeared in the last 7 days gets a lower `novelty_score` than a genuinely new story. `entity_history` ingests from ALL collected articles, not just selected KeyIssues | `test_selector.py` seeds `entity_history` + synthetic articles; warmup case explicitly tested |
| **AC10a** | Every live run's request payload includes `cache_control: {"type":"ephemeral"}` on the system block for both Call A and Call B | Deterministic: `test_summarizer.py` asserts on the request dict |
| **AC10b** | On the second Call A request within 5 minutes (same system prefix), `cache_read_input_tokens ≥ 500` | Manual live test script; best-effort for Call B (acknowledged server-side variability). Within-TTL only; day-over-day is not asserted. |
| AC11 | `.eml` opens cleanly in at least one of Outlook / Apple Mail / Thunderbird with all links clickable | Manual one-time check |
| AC12 | If fewer than 3 feeds **each contributed ≥1 article after parsing and filtering**, the script aborts with a clear error BEFORE any LLM call | `test_collector.py` mocks feeds to return 0 or only-filtered-out articles on all but 2 feeds; asserts `SystemExit` and zero LLM invocations |
| AC13 | `rerender <run_id>` regenerates `.eml` from persisted `call_b_response.json` + `key_issues.json` with zero API calls | e2e test |
| **AC14** | Renderer displays Python-computed scores (novelty/diffusion/combined), not LLM-written numbers. All 4 LLM-response pydantic models (`CallAClusterOut`, `CallAResponse`, `BriefingItem`, `LLMBriefing`) use `ConfigDict(extra="forbid")`. **Test (explicit):** load `mock_call_b_fabricated_score.json` which injects `novelty_score: 0.9` into one `BriefingItem`; `LLMBriefing.model_validate(...)` raises `pydantic.ValidationError` | `test_summarizer.py::test_ac14_score_injection_rejected`; assert exception class is `pydantic.ValidationError`, not `ValueError` |
| **AC15** | Per-stage durations logged to `runs.stage_durations_json`; **absolute hard caps**: `collect < 180s AND select < 10s AND call_a < 45s AND call_b < 120s AND render < 5s` | `test_end_to_end_dry_run.py` reads `runs.stage_durations_json` and asserts all 5 caps. Live run's `runs.stage_durations_json` checked at end of `run` command; on any cap breach, log a WARN to `runs.notes` (non-fatal — breach of a single stage doesn't abort a successful run). |
| **AC16 (new, R1)** | Call A response that merges an article from `food` with one from `beauty` (spanning >2 pre-cluster categories is the failure case — this 2-category test confirms the boundary tolerates 2 but rejects 3) → **variant A:** mock merges 3 distinct-category candidates, `merge_candidate_clusters()` unfolds back to originals and logs `category_span_violation` to `runs.notes`. Likewise, a Call A merge where the union `published_at` span exceeds 72h → unfold + log `time_span_violation`. | `test_summarizer.py::test_r1_category_span_violation` + `test_r1_time_span_violation` |
| **AC17 (new, R6)** | Article with body `'Samsung Galaxy S26가 한국에 출시됐다'` extracts `Samsung` and `Galaxy` via EN regex. Brand-dict entry `자라 → Zara` test: article mentioning `자라` yields canonical `Zara`. Both extractors run regardless of `article.language`. | `test_collector.py::test_r6_cross_language_entity_extraction` |

### Per-stage performance budgets (design targets + AC15 hard caps)

| Stage | Design target | **AC15 hard cap** | Rationale |
|---|---|---|---|
| collect | 60s | **180s** | Bounded by per-host 1req/s + RSS count (~15 feeds) + enrichment on top-40 |
| select | 2s | **10s** | Pure Python on a few hundred articles |
| call_a | 15s | **45s** | Haiku, ~2500 input tokens, ~800 output tokens |
| call_b | 45s | **120s** | Sonnet, ~2800 input tokens, ~1500 output tokens |
| render | 1s | **5s** | Jinja2 + stdlib `email` |
| **total** | ~2 min | **<10 min** (AC7) | |

**AC15 wording change from v2:** the v2 metric `max(stage) / total < 0.5` falsely failed on slow-API days (e.g. Call B taking 90s when all other stages combined took 15s gave a ratio of 0.86 even though the run succeeded in <2min). v3 replaces it with **absolute per-stage caps** logged to `runs.stage_durations_json`. Design targets in the "target" column drive provisioning; hard caps in the AC15 column are the test assertions.

---

## 8. ADR (revised)

**Decision:** Build a local Python 3.11+ CLI (`python morning_brief.py`) that:
1. Collects via RSS with cross-language entity ingest from every article (R6).
2. Pre-clusters same-language duplicates with `rapidfuzz`.
3. Scores novelty (7-day warmup aware) + diffusion in Python.
4. Calls **Haiku (Call A)** to re-cluster across languages and canonicalize; with **R1 sanity checks** (category-span + time-span) inside `summarizer.merge_candidate_clusters()` guarding the Call-A → scorer handoff.
5. Recomputes scores in Python on merged clusters.
6. Applies the **Blocker-3 section rule** (category renders iff ≥1 cluster at threshold; misc bucket for failures).
7. Calls **Sonnet (Call B)** to write a Korean briefing whose JSON contains no numeric scores; **all 4 LLM-response pydantic models use `ConfigDict(extra="forbid")`** so fabricated score fields raise `ValidationError` (Blocker 1).
8. Renderer injects Python-computed scores into the HTML and builds a `.eml` file.
9. **Call A failure policy (R3):** HTTP or schema errors retry once then abort with `SystemExit(3)`; no silent fallback to pre-cluster candidates.
10. SQLite holds cross-day state including `entity_history`.

**Drivers:**
- Korean output quality → Sonnet 4.6 for Call B.
- Cross-lingual clustering satisfying AC8 → LLM-based re-cluster (Haiku) with sanity-check guardrails (R1).
- Editorial transparency (Principle 3) → Python-authoritative scores; pydantic `extra="forbid"` prevents LLM-written numbers from being silently accepted (Blocker 1).
- Testable acceptance → AC15 uses absolute caps (not ratios), AC8 uses a frozen fixture pair (R2), AC14 asserts explicit `ValidationError` class.
- Cache friendliness **within the 5-min TTL** — stable system prefixes; day-over-day hits are not load-bearing.

**Alternatives considered:**
- **Single-call pipeline (v1 proposal)** — rejected: (a) `rapidfuzz`-only clustering demonstrably fails on cross-lingual pairs, breaking AC8; (b) single LLM call conflates 5 concerns; (c) LLM-written scores violate Principle 3.
- **Three-call pipeline** — rejected: ranking is deterministic Python, dedicated LLM call adds latency without gain.
- **Embedding-based clustering (D5 row, new in v3)** — deferred to FU3: multilingual-MiniLM via `sentence-transformers` handles cross-lingual matching deterministically without LLM latency, but adds heavy deps (PyTorch or a second API) and still requires a separate canonicalization step. At MVP scale, Haiku Call A is cheaper and gives canonical label + category confirmation in one call.
- **GPT-4.1 / Gemini 2.5 Pro** — rejected for Korean fluency / caching control reasons (see v1 §1 D1, unchanged).
- **Gmail API Phase-1 delivery** — deferred (see v1 §1 D2).
- **JSON-file storage** — rejected (see v1 §1 D4).
- **Ratio-based per-stage AC (v2 AC15)** — rejected in v3: falsely fails on slow-API days even when the run succeeds. Absolute caps are more robust.
- **Fallback to pre-cluster candidates on Call A failure** — rejected in v3 (R3): silent AC8 regression. Explicit abort preferred.

**Why chosen:** Two-call pipeline with named handoff + sanity checks is the minimum structural change that makes each of AC3 / AC8 / AC9 / AC14 / AC16 independently satisfiable and testable. `extra="forbid"` on all LLM response models makes Principle 3 structurally enforceable, not just documented. Absolute per-stage caps (AC15) test the right thing. The R2 frozen AC8 fixture makes cross-lingual merging a deterministic pipeline assertion, not a "live smoke test" subject to API availability.

**Consequences:**
- (+) Cross-lingual duplicates actually merge (AC8 passes deterministically on a frozen fixture).
- (+) Score numbers in the final email are deterministic and reproducible from SQLite state.
- (+) Fabricated LLM score fields raise `ValidationError` at schema-load time — impossible to ship silently.
- (+) R1 sanity checks catch pathological Call A outputs (merging food + beauty + hospitality into one cluster) without aborting the run.
- (+) R3 abort policy makes Call A failure loud and inspectable (raw response persisted).
- (+) Each pipeline stage is debuggable in isolation; persisted JSON per call supports `rerender` + targeted retries.
- (−) Two round-trips instead of one (~2–4 extra seconds); well inside the AC15 caps.
- (−) Two prompts to maintain (mitigated: both are stable content in `prompts/`).
- (−) Day-1 briefing is diffusion-weighted by design (warmup). User sees some low-signal stories the first morning; stabilizes after 7 days. Documented.
- (−) Day-over-day cache hits are best-effort, not guaranteed (softened P4).

**Follow-ups:**
- FU1: Measure first-week Call A accuracy on cross-lingual pairs. If recall < 80%, escalate Call A model from Haiku to Sonnet (one-line config change).
- FU2: Gmail Drafts delivery (Phase 2).
- FU3: Embedding-based clustering (`paraphrase-multilingual-MiniLM-L12-v2`) as a Call A replacement if LLM latency or cost becomes an issue.
- FU4: Windows Task Scheduler template + macOS launchd plist.
- FU5: Expand `config/brands.txt` from first-week error analysis.
- FU6: Consider merging `call_a_system.md` and `call_b_system.md` into a single shared glossary block for double-cache reuse (micro-optimization).
- FU7: If R1 sanity rejections become frequent (>5% of Call A outputs), tighten the Call A system prompt rather than tuning the thresholds.

---

## 9. Implementation Phases

### Phase 1 — MVP vertical slice (1–2 days)
**Goal:** user runs one command, gets a reviewable Korean `.eml` in `out/`, in <10 minutes of wall-clock time.
- Steps 1–8 from §3.
- AC1–AC17 all passing (AC10b and AC11 are best-effort/manual; rest are automated).
- Windows 11 + Git Bash primary target.

### Phase 2 — Polish (post-MVP)
- Gmail Drafts delivery.
- Scheduler helpers (Windows Task Scheduler XML + macOS `launchd` plist).
- Feed health dashboard subcommand.
- `insight_box` historical memory (last 3 days' insight boxes fed into Call B prompt).
- Call A → Sonnet escalation based on first-week measurements.

### Phase 3 — Explicitly out of scope
- Per-client personalization.
- Web dashboard / subscription UI / auth.
- Instagram/TikTok crawling.
- 20+ recipient broadcast infra.
- Realtime alerts.

---

## Open Questions (remaining)

Carried over from v1/v2 (no new items introduced in v3):

- [ ] OQ1: Subject-line A/B variants vs single canonical form (dynamic join already specified per Blocker 3).
- [ ] OQ2: Seed `config/brands.txt` with ~50 brands vs ship empty.
- [ ] OQ3: Time zone for `generated_at` — KST fixed (proposed) vs local.
- [ ] OQ5: Provider abstraction day-1 vs Anthropic-only for Phase 1.
- [ ] OQ6: Call A model escalation policy (Haiku → Sonnet auto-escalation if AC8 live recall <80% after first week; confirm user preference vs Haiku-only cost-cap or Sonnet-from-day-1).

OQ4 remains resolved (misc "기타 관찰" bucket, formalized as the Blocker-3 rule in v3 §5.4).

---

## Planner dissent

None. All 3 blockers and all 6 recommendations were accepted without pushback. The reasoning in each is sound:

- **Blocker 1** is a pydantic v2 semantics gotcha the v2 test would have silently passed. Fix is mechanical and correct.
- **Blocker 2** correctly identifies that the ratio metric penalizes the wrong thing. Absolute caps are the right test.
- **Blocker 3** is a real ambiguity in v2 that an executor would have had to guess at; picking the "≥1 cluster = section" rule is the reader-friendliest choice (a category present in user's head should not vanish into misc just because it only has 1 story today).
- **R1** adds a meaningful guardrail against pathological LLM output with minimal code cost.
- **R2** converts a fuzzy "live smoke test" AC into a deterministic fixture assertion — strictly better.
- **R3** closes a quiet fallback path that would have regressed AC8 silently.
- **R4** names the handoff helper, which was under-specified in v2.
- **R5** tightens principles to match the actual architecture.
- **R6** makes the EN+KO extractor policy explicit for mixed-language articles (a real case in Korean tech/consumer press).

One minor re-framing of **Minor polish D5 row**: the embedding-clustering alternative is documented honestly. It is not a pretending-fair option — it is a legitimate Phase-2 path (FU3), just not the right MVP choice given deps and the fact that Haiku Call A gives the canonical Korean label for free. The v3 D5 row calls this out explicitly.
