# Morning Consumer Trend Briefing — Plan v2

**Source spec:** `.omc/specs/deep-interview-morning-consumer-trend-briefing.md` (ambiguity 19.5%, PASSED)
**Supersedes:** `.omc/plans/morning-briefing-plan-v1.md` (MAJOR_REVISIONS from Architect)
**Plan type:** RALPLAN-DR consensus plan, revision 2
**Target:** Local Python 3.11+ CLI, Windows 11 primary, Git Bash shell
**Scope:** MVP end-to-end vertical slice, 1–2 days of focused work

## Change log vs v1 (for reviewer skim)

1. **Two-call LLM pipeline** — Call A (Haiku, cluster+canonicalize) then Call B (Sonnet, write briefing). Single call in v1 conflated 5 tasks. This also fixes cross-lingual clustering, which v1's `rapidfuzz` could not do.
2. **Renderer-side score display** — `why_selected` removed from LLM output; renderer reads Python-computed `combined_score` / `novelty_score` / `diffusion_score` directly.
3. **Novelty ingest fix** — `entity_history` now ingests entities from every collected article (not just selected KeyIssues) with `first_seen_at`. 7-day warmup clause documented with explicit day-1 behavior.
4. **File structure collapsed** — 6 top-level code modules (was ~20). Prompts remain as two markdown files in a `prompts/` content folder.
5. **OQ4 resolved** — singletons and sub-threshold categories aggregate into a single "기타 관찰" section.
6. **.gitignore + PII handling** — verbatim .gitignore in Step 1; `REDACT_RECIPIENTS=1` env var documented.
7. **AC10 split** — AC10a (deterministic: `cache_control` present) + AC10b (server-side: `cache_read_input_tokens>0` on second run within 5min).
8. **Per-stage perf budgets** — concrete seconds per stage, logged to `runs.stage_durations_json`, asserted no stage >50% of total budget.
9. **Smaller fixes** — Google News redirect unwrapping, Korean postposition list expanded, pydantic semantic validation on LLM output, `schema_version` in persisted response, `rich` removed, dynamic subject line.

---

## 1. RALPLAN-DR Summary (revised)

### Principles (5, revised)

1. **Simplicity over automation** — MVP is one `python morning_brief.py` invocation. No scheduler, no daemon, no web UI. Automation is a Phase 2 wrapper. (unchanged from v1)
2. **LLM does translation + summarization in one pass** — clarified: "one pass" means one orchestrated pipeline (one invocation of `morning_brief.py`), **not** one prompt. Two sequential LLM calls — Call A (cluster + canonicalize) and Call B (write briefing) — are still one pass. The human never sees or edits LLM intermediate state.
3. **Editorial transparency** — every `KeyIssue` in the draft carries its novelty / diffusion / combined scores as computed by `selector.py`, rendered into the HTML by the renderer directly from Python values. The LLM never writes score numbers; fabricated scores are structurally impossible.
4. **Cache-hit-friendly prompt shape** — Call A's system prefix (clustering rules + category definitions + entity extraction instructions, ~1500 tokens) is stable across daily runs and dev iterations. Call B's system prefix (editorial voice + output schema + examples, ~1800 tokens) is also stable. Cache now genuinely pays off day-over-day for Call A, not just within the 5-minute dev window.
5. **Reversible storage** — all intermediate artifacts (raw articles, entity_history deltas, clusters, call_a_response.json, call_b_response.json, .eml) are written to disk so any single stage can be re-run without re-fetching.

### Decision Drivers (top 3, unchanged)

1. **Korean output quality** — the user forwards this to Korean-speaking clients; bad Korean = the whole product fails.
2. **Fast time-to-first-valuable-output** — reviewable draft on Day 2 of work, not Day 10.
3. **Low, predictable operating cost** — single laptop, prompt caching mandatory, no per-user infra.

### Viable Options per Key Decision

#### D1. LLM choice — unchanged from v1 (Claude, swappable)

**Choice: Claude family.** Call A = Haiku 4 for speed/cost; Call B = Sonnet 4.6 for Korean fluency. Swappable via `LLM_CALL_A_MODEL` / `LLM_CALL_B_MODEL` env vars.

Full alternatives matrix (Claude Sonnet vs GPT-4.1 vs Gemini 2.5 Pro) identical to **v1 §1 D1** — not repeated.

#### D2. Email delivery mechanism — unchanged from v1

`.eml` file for Phase 1; Gmail API stubbed for Phase 2. See **v1 §1 D2**.

#### D3. News collection method — unchanged from v1

RSS-first + targeted OpenGraph enrichment on top-N. See **v1 §1 D3**.

#### D4. Storage — unchanged from v1

SQLite at `.omc/state/briefing/briefing.db`. See **v1 §1 D4**.

#### D5. LLM pipeline: single call vs two-call  ← NEW

| Option | Pros | Cons |
|---|---|---|
| **Single call (v1 proposal)** | Simpler code; one network round-trip; one prompt to tune | Conflates translate + cluster + rank + write + categorize — opaque failure modes; bad output on any one task taints all others; `rapidfuzz`-based clustering cannot merge cross-lingual duplicates (token overlap is ~0 between "숏폼 화장품 리뷰" and "short-form beauty reviews"); LLM-written score numbers drift from Python-computed scores → violates Principle 3 |
| **Two-call (chosen)** | Call A (Haiku) handles re-clustering and canonicalization where cross-lingual semantic equivalence is trivial for an LLM; Call A's prefix is stable day-over-day (clustering rules never change) → real cache wins; Call B (Sonnet) focuses on editorial output only; each call's failure mode is inspectable and retryable independently; Python-computed scores feed directly into renderer (Principle 3 bit-exact) | Two round-trips (~2–4 extra seconds); two prompts to maintain; need to persist both responses |
| Three-call (cluster → rank → write) | Even more separation of concerns | Overkill for MVP; ranking is deterministic Python math, not an LLM task; extra latency without commensurate quality gain |

**Choice: Two-call.** Rationale: the spec explicitly names cross-lingual input (한+영 혼합) and repetition/diffusion across sources as acceptance criteria. `rapidfuzz` demonstrably cannot satisfy AC8 for translated duplicates. Haiku can. Two calls also make AC3 (exec_summary exactly 3 lines) and AC9 (novelty correctness) debuggable in isolation.

**Mild pushback to Architect noted:** v2 defaults Call A to Haiku as proposed, but if AC8 live-test fails on cross-lingual pairs in practice, the fallback is a one-line config swap to Sonnet. No architectural change. Ring-fenced risk.

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
         └────────┬─────────┘
                  │  Article[]  → SQLite.articles
                  │  → ENTITY INGEST: every article's entities logged to
                  │     SQLite.entity_history with first_seen_at
                  ▼
         ┌──────────────────┐
         │  selector.py     │  Python-only pre-clustering (cheap same-lang
         │                  │  dedup via rapidfuzz) + novelty + diffusion
         │                  │  scores → candidate cluster list
         └────────┬─────────┘
                  │  CandidateCluster[]
                  ▼
         ┌──────────────────┐
         │  summarizer.py   │  Call A (Haiku): re-cluster across languages
         │                  │    + canonicalize entity + confirm category
         │                  │  → final Cluster[] with cross-lingual merges
         │                  │  ← Python recomputes novelty/diffusion on
         │                  │    the merged clusters (authoritative scores)
         │                  │  → picker selects top KeyIssue[]
         │                  │  Call B (Sonnet): write Korean briefing JSON
         │                  │    (no score numbers — only prose + links)
         └────────┬─────────┘
                  │  LLMBriefing (exec_summary + sections + insight_box)
                  │  + KeyIssue[] with Python scores
                  ▼
         ┌──────────────────┐
         │  renderer.py     │  Jinja2 HTML; renderer injects
         │                  │  {novelty, diffusion, combined} from Python
         │                  │  into each item; builds EmailMessage → .eml
         └────────┬─────────┘
                  │  out/briefing_YYYY-MM-DD.eml
                  ▼
                (user opens, reviews, sends)
```

### 2.2 File / directory structure (6 code modules)

```
morning_brief/
├── pyproject.toml                 # deps (see Step 1)
├── README.md                      # Windows + Git Bash setup
├── .env.example
├── .gitignore                     # verbatim contents in Step 1
├── morning_brief.py               # CLI entry (argparse): run / dry-run / rerender
├── config/
│   ├── sources.yml                # RSS feeds (see v1 §6; additions noted below)
│   ├── categories.yml             # 5 categories + ko/en keywords + exclusions
│   └── editorial.md               # editorial voice guide
├── morning_brief/
│   ├── __init__.py
│   ├── models.py                  # pydantic: Article, Cluster, KeyIssue, LLMBriefing, ...
│   ├── db.py                      # SQLite bootstrap + DAO
│   ├── collector.py               # RSS fetch + redirect unwrap + OG enrichment + entity ingest
│   ├── selector.py                # pre-cluster + novelty + diffusion + picker
│   ├── summarizer.py              # Call A + Call B orchestration + pydantic validation
│   ├── renderer.py                # Jinja2 render + .eml build
│   └── prompts/                   # content, not code
│       ├── call_a_system.md       # stable ~1500 tokens — clustering rules
│       ├── call_a_user.j2         # per-run article bundle template
│       ├── call_b_system.md       # stable ~1800 tokens — editorial voice + schema
│       └── call_b_user.j2         # per-run selected cluster bundle template
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── sample_rss.xml
│   │   ├── sample_articles.json
│   │   ├── mock_call_a_response.json
│   │   └── mock_call_b_response.json
│   ├── test_collector.py
│   ├── test_selector.py           # covers clustering + scoring + picker
│   ├── test_summarizer.py         # covers prompt assembly + pydantic validation
│   ├── test_renderer.py
│   └── test_end_to_end_dry_run.py
└── out/                           # .eml files (gitignored)
```

**Count: 6 top-level code modules** (`models`, `db`, `collector`, `selector`, `summarizer`, `renderer`) plus the CLI entry at repo root. Prompts are content files, not code modules.

State lives under `.omc/state/briefing/` (`briefing.db`, per-run debug JSON dumps).

### 2.3 Key data schemas (pydantic, revised)

```python
# morning_brief/models.py  (illustrative — not code to write now)

class Article:
    id: str
    title: str
    source_name: str
    source_type: Literal["TraditionalMedia","SpecializedMedia","CuratedTrendReport"]
    url: str
    canonical_url: str        # after Google News redirect unwrap
    language: Literal["ko","en"]
    published_at: datetime    # UTC
    category: str | None
    raw_summary: str
    enriched_text: str | None
    fetched_at: datetime
    extracted_entities: list[str]   # populated at collect time, fed into entity_history

class CandidateCluster:       # output of selector pre-clustering (same-lang only)
    id: str
    category: str
    article_ids: list[str]
    representative_title: str

class Cluster:                # after Call A re-clustering (may merge across langs)
    id: str
    category: str             # category_confirmed by Call A
    canonical_entity_ko: str  # e.g. "숏폼 뷰티 리뷰" — single Korean label
    article_ids: list[str]
    is_cross_lingual_merge: bool
    diffusion_score: float    # recomputed in Python post Call A
    novelty_score: float      # recomputed in Python post Call A
    combined_score: float

class KeyIssue:
    cluster_id: str
    category: str
    canonical_entity_ko: str
    novelty_score: float
    diffusion_score: float
    combined_score: float
    article_bundle: list[Article]  # capped at 5 articles into Call B prompt

class LLMBriefing:            # Call B output — NO score numbers, NO why_selected
    schema_version: Literal["v2"]
    exec_summary_ko: list[str]        # exactly 3 lines (pydantic-enforced)
    sections: dict[str, list[BriefingItem]]
    misc_observations_ko: list[BriefingItem] | None   # "기타 관찰" bucket
    insight_box_ko: str

class BriefingItem:
    cluster_id: str           # MUST match a KeyIssue.cluster_id (renderer joins)
    title_ko: str
    summary_ko: str           # 1-3 sentences
    # scores are NOT here — renderer injects from KeyIssue
    is_paywalled: bool
```

---

## 3. Concrete Implementation Steps (ordered, file-level)

### Step 1 — Project scaffold & config
- `pyproject.toml` — deps: `feedparser>=6.0`, `httpx>=0.27`, `beautifulsoup4>=4.12`, `pydantic>=2.6`, `jinja2>=3.1`, `pyyaml>=6.0`, `anthropic>=0.40`, `python-dotenv>=1.0`, `rapidfuzz>=3.6`. Dev: `pytest`, `pytest-mock`. **Removed:** `rich`.
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
- `.gitignore` (verbatim):
  ```
  # Python
  __pycache__/
  *.pyc
  .venv/
  *.egg-info/
  build/
  dist/

  # Environment / secrets
  .env
  .env.*
  !.env.example

  # Briefing output (may contain recipient emails)
  out/

  # Local state (contains cached LLM responses and per-run artifacts)
  .omc/state/briefing/

  # Editor
  .vscode/
  .idea/
  *.swp
  ```
- `config/categories.yml`, `config/sources.yml`, `config/editorial.md` — see v1 §6 for the sources list; v2 adds `allthingsd_foodnavigator` and `cosmeticsbusiness.com` feeds if available (researcher to verify). Otherwise unchanged.
- **PII note** (in README): `out/*.eml` contains recipient email addresses; set `REDACT_RECIPIENTS=1` to replace the `To:` header with `__REDACTED__` for screenshot sharing.
- **Depends on:** nothing.

### Step 2 — Data layer
- `morning_brief/models.py` — pydantic models from §2.3.
- `morning_brief/db.py` — SQLite schema, idempotent `bootstrap()`. Tables:
  - `articles` (id, canonical_url, title, source_name, source_type, lang, category, published_at, raw_summary, enriched_text, fetched_at)
  - `entity_history` (entity_text, entity_norm, first_seen_at, last_seen_at, total_occurrences, article_ids_json) — **populated from every collected article**
  - `clusters` (id, category, canonical_entity_ko, is_cross_lingual_merge, novelty_score, diffusion_score, combined_score, created_at)
  - `cluster_members` (cluster_id, article_id)
  - `runs` (id, started_at, completed_at, run_duration_seconds, stage_durations_json, llm_usage_json, schema_version, notes)
- **Depends on:** Step 1.

### Step 3 — Collector (with entity ingest)
- `morning_brief/collector.py`:
  - Iterate `sources.yml`, fetch via `httpx` (timeout 8s, 3 retries, 1 req/s per host), parse with `feedparser`.
  - **Google News RSS redirect unwrap**: after fetching, the `link` field is a `news.google.com/rss/articles/...` redirect URL. Follow with a HEAD request (or lightweight GET + meta-refresh parse) and store the publisher's canonical URL in `Article.canonical_url`. Fall back to the google link if unwrap fails.
  - Within-run dedup by `canonical_url`.
  - Category assignment: source metadata first; fallback keyword match on title+summary using `config/categories.yml`.
  - **Enrichment** (top-N by recency, N=40): fetch HTML, parse `<meta property="og:description">` and first `<p>`. Skip if paywall markers detected.
  - **Entity extraction** (runs on EVERY article, not just selected ones):
    - English: regex `[A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]+){0,3}`.
    - Korean: strip expanded postposition list — `은/는/이/가/을/를/의/에/와/과/로/으로/에서/부터/까지/보다/처럼/만/도` — then match brand tokens from `config/brands.txt` + sequences of 2+ Hangul chars preceded by quotes or followed by `은/는/이/가`.
    - Normalize to lowercase/NFC.
  - **Entity ingest**: for each extracted entity, upsert into `entity_history`. If `entity_norm` is new, set `first_seen_at = today`; otherwise update `last_seen_at` and increment `total_occurrences`.
- **Depends on:** Step 2.
- **Acceptance:** fixture RSS → ≥5 `Article` with correct categories AND `entity_history` is populated from every article (not just future-selected ones). Google News fixture with redirect URL → `canonical_url` differs from `url`.

### Step 4 — Selector (pre-cluster + score + pick)
- `morning_brief/selector.py`:
  - **Same-language pre-cluster** via `rapidfuzz.fuzz.token_set_ratio ≥ 75` on normalized titles, single-linkage within category + 72h window. This catches cheap within-language duplicates before Call A.
  - **Scoring** (applied to candidate clusters):
    - `diffusion_score` — `0.6 * min(n_sources / 5, 1.0) + 0.4 * source_type_diversity` (unchanged from v1).
    - `novelty_score` — **7-day warmup aware**:
      - For each cluster, pick the "primary entity" (highest per-article co-occurrence across the cluster).
      - Query `entity_history` for `first_seen_at`.
      - If `first_seen_at >= today - 7d` **and** DB started within the last 7 days: this is the warmup window. Shift weights toward diffusion: `combined = 0.3*novelty + 0.7*diffusion`.
      - Otherwise (steady state): `combined = 0.55*novelty + 0.45*diffusion`.
      - Actual novelty scalar: `novelty = max(0, 1 - 0.15 * prior_day_hits_last_7d)`.
      - **Day-1 behavior (documented):** on the first run, every entity is "new" so novelty would be 1.0 for everything. Warmup formula mitigates this by weighting diffusion. The briefing on day 1 is explicitly diffusion-driven.
  - **Picker**: top-N per category (`MIN_PER_CAT=2`, `MAX_PER_CAT=3`), global cap 13. Category with <2 clusters after Call A → items flow into `misc_observations_ko` ("기타 관찰") instead of being dropped or placeholder'd.
- **Depends on:** Step 3.
- **Acceptance:**
  - Synthetic test: 2 same-lang near-dupes merge; different-lang pair is *left unmerged* at this stage (that's Call A's job).
  - `test_selector_novelty_warmup` asserts the 7-day warmup weight shift actually kicks in when `entity_history` has <7 days of data.

### Step 5 — Summarizer (two-call pipeline)
- `morning_brief/summarizer.py` orchestrates both calls. `morning_brief/prompts/` holds stable prompt content.

#### 5a. Call A — Cluster + Canonicalize (Haiku)

**System prefix (~1500 tokens, `prompts/call_a_system.md`, `cache_control: ephemeral`):**
```
ROLE: You are a Korean-fluent clustering editor for a consumer-trend briefing.

TASK: Given N candidate article clusters (already pre-grouped by same-language
title similarity), decide which clusters actually describe THE SAME UNDERLYING
STORY or TREND across languages, and emit a canonical Korean label for each
merged group.

CLUSTERING RULES:
 - Merge across languages when the core entity, event, or trend is semantically
   equivalent. Example: "Zara launches AI-generated campaign" and
   "자라, AI 생성 캠페인 공개" → same story.
 - Merge across sources when the trend label is equivalent, even if angles
   differ. Example: "short-form beauty reviews on YouTube" and "숏폼 화장품
   리뷰" → same trend.
 - DO NOT merge when the only overlap is a category or a shared brand
   mentioned incidentally.

CANONICALIZATION:
 - canonical_entity_ko: a 2–6 word Korean noun phrase naming the story/trend.
 - category_confirmed: pick exactly one of Food / Beauty / Fashion / Living /
   Hospitality. If ambiguous, pick the dominant one and set
   is_cross_lingual_merge accordingly.

5 CATEGORY DEFINITIONS:
 - Food: 식품·음료·외식 소비자 행동 및 트렌드 …
 - Beauty: 화장품·스킨케어·퍼스널케어 …
 - Fashion: 의류·액세서리·패션 유통 …
 - Living: 라이프스타일·홈·리빙 상품 …
 - Hospitality: 호텔·여행·숙박 경험 …
 (each ~80 tokens with 2 example keywords)

ENTITY EXTRACTION:
 - Return up to 3 key entities per cluster (brand, product line, technology,
   behavior pattern).

OUTPUT CONTRACT:
 - Respond with JSON matching exactly: { "clusters": [ { "input_cluster_ids":
   [...], "category_confirmed": "...", "canonical_entity_ko": "...",
   "is_cross_lingual_merge": bool, "key_entities": [...] } ] }
 - Every input cluster_id appears in EXACTLY ONE output cluster.
 - No commentary outside the JSON.

FEW-SHOT: 2 examples (one cross-lingual merge, one correct non-merge).
```

**User payload (per-run, `prompts/call_a_user.j2`):** titles + raw_summary + source + lang only for each candidate cluster — NO article bodies. Keeps the variable part small.

**Response handling:** pydantic validation; if `input_cluster_ids` coverage is incomplete or duplicated → structured retry with a targeted error message. One retry only.

#### 5b. After Call A, before Call B — Python recomputes scores

The selector's novelty/diffusion scores are recomputed on the Call-A-merged clusters (a merged cluster's `n_sources` is the union across merged candidates). These are authoritative and passed to the renderer directly.

#### 5c. Call B — Write Briefing (Sonnet)

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

SCORE POLICY: Do NOT write any numeric score. Score columns are handled by
the renderer. Focus on prose quality.

OUTPUT SCHEMA (strict, pydantic-validated on our side):
 { "schema_version": "v2",
   "exec_summary_ko": [str, str, str],
   "sections": { "Food": [...], "Beauty": [...], "Fashion": [...],
                 "Living": [...], "Hospitality": [...] },
   "misc_observations_ko": [BriefingItem] | null,
   "insight_box_ko": str }
 BriefingItem = { "cluster_id": str, "title_ko": str, "summary_ko": str,
                  "is_paywalled": bool }
 - cluster_id MUST match one of the input KeyIssue cluster_ids exactly.
 - title_ko / summary_ko MUST be Korean (>=80% Hangul excluding
   proper nouns).
 - Omit a section only if its KeyIssue list is empty.
 - Source URLs are NOT in your output; renderer joins them from KeyIssue.

FORBIDDEN:
 - Inventing source_url fields.
 - Changing cluster_id or inventing new clusters.
 - Numeric scores anywhere.
 - Emojis in the body.

FEW-SHOT: 1 complete good briefing (~600 tokens) + 1 bad briefing with
annotated problems.
```

**User payload (`prompts/call_b_user.j2`):** selected `KeyIssue[]` with category, canonical_entity_ko, and full article bundles (title, source_name, lang, published_at, raw_summary, enriched_text, canonical_url, is_paywalled). NO score numbers in user payload — they're injected by the renderer.

**Response handling:**
- pydantic semantic validation:
  - `exec_summary_ko` length exactly 3.
  - Each `cluster_id` exists in the input KeyIssue set.
  - Body Hangul ratio ≥ 80%.
  - No `http`/`www.` tokens in `summary_ko` / `title_ko` (those belong in renderer).
- On any validation failure, send **one structured retry** with the specific pydantic error message appended to the user prompt. If retry also fails, abort with a clear error and persist the raw response to `.omc/state/briefing/runs/<run_id>/call_b_response_raw.json` for debugging.

**Caching:** both Call A and Call B use `cache_control: {"type":"ephemeral"}` on the system block. AC10a asserts this is always present.

**Persisted artifacts per run:**
- `call_a_request.json`, `call_a_response.json` (with `schema_version: "v2"`)
- `call_b_request.json`, `call_b_response.json` (with `schema_version: "v2"`)

**DRY_RUN=1:** skips both network calls, loads `tests/fixtures/mock_call_a_response.json` and `mock_call_b_response.json`.

- **Depends on:** Step 4.
- **Acceptance:**
  - Call A fixture test: 2 input clusters with cross-lingual-equivalent titles merge; unrelated clusters don't.
  - Call B pydantic validation test: fabricated cluster_id → retry triggered with targeted error message.
  - DRY_RUN path produces valid `LLMBriefing` from fixtures with zero API calls.

### Step 6 — Renderer (injects Python scores)
- `morning_brief/renderer.py`:
  - Joins `LLMBriefing.sections[*]` items by `cluster_id` with the full `KeyIssue[]` list (which holds Python-computed scores + source URL list).
  - Jinja2 template (`prompts/` is for LLM prompts only; the HTML template is inline in `renderer.py` as a string constant or a sibling `briefing.html.j2` — placement decision: sibling file at `morning_brief/briefing.html.j2`).
  - Each item renders: `title_ko`, `summary_ko`, score pills (e.g. `신규성 0.82 · 확산도 0.71`), source link list (max 3), `[요약본]` tag if paywalled.
  - **Dynamic subject line**: build from sections actually present. Example: if Hospitality has zero items today and misc has some, subject is `"[소비재 트렌드 조간] 2026-04-18 (Food/Beauty/Fashion/Living · 기타 관찰)"`. Never list an empty section.
  - Builds `EmailMessage` (multipart/alternative plain + HTML) → writes `out/briefing_YYYY-MM-DD.eml`.
  - **PII redaction**: if `REDACT_RECIPIENTS=1`, write `To: __REDACTED__` and omit recipient addresses from the body footer.
  - Prints absolute output path to stdout via stdlib `print` (no `rich`).
- **Depends on:** Step 5.
- **Acceptance:**
  - Rendered HTML shows Python-computed scores, not LLM numbers.
  - Subject line matches dynamic-join rule on a fixture with a missing category.
  - `.eml` opens cleanly in Outlook/Thunderbird/Apple Mail.

### Step 7 — CLI + end-to-end wiring
- `morning_brief.py` at repo root — argparse subcommands:
  - `run` — full pipeline.
  - `dry-run` — `DRY_RUN=1`, mocked both LLM calls.
  - `rerender <run_id>` — re-run renderer from persisted Call B response + KeyIssue snapshot; zero API calls.
  - `--limit-per-cat N` override.
- Per-run debug artifacts: `.omc/state/briefing/runs/<YYYY-MM-DD-HHMM>/` with all JSON dumps + the final `.eml`.
- `stage_durations_json` populated for every run (collect / select / call_a / call_b / render).
- **Depends on:** Step 6.
- **Acceptance:**
  - `python morning_brief.py dry-run` exits 0 in <30s on fixtures with zero network calls.
  - `runs.stage_durations_json` has all 5 stages populated.

### Step 8 — Tests + smoke validation
- `tests/test_collector.py` — RSS parse + Google News redirect unwrap + entity ingest on every article.
- `tests/test_selector.py` — pre-clustering, novelty warmup, scoring, picker.
- `tests/test_summarizer.py` — prompt assembly, pydantic validation, retry path, cache_control presence.
- `tests/test_renderer.py` — dynamic subject line, score injection, PII redaction mode.
- `tests/test_end_to_end_dry_run.py` — full pipeline on fixtures, asserts all AC that are automatable.
- README with Windows/Git Bash setup: `python -m venv .venv && source .venv/Scripts/activate && pip install -e . && cp .env.example .env && python morning_brief.py dry-run && python morning_brief.py run`.
- **Depends on:** Step 7.
- **Acceptance:** `pytest` runs green locally with zero network calls.

---

## 4. Prompt Engineering

Summary of shape (detail in Step 5):

| Call | Model | System prefix | User payload | Cached? | Output |
|---|---|---|---|---|---|
| A | Haiku 4 | ~1500 tokens (clustering rules + category defs + entity extraction + 2 few-shots) | Candidate clusters: titles + raw_summary + source + lang only | Yes (`ephemeral`) | `{clusters: [{input_cluster_ids, category_confirmed, canonical_entity_ko, is_cross_lingual_merge, key_entities}]}` |
| B | Sonnet 4.6 | ~1800 tokens (editorial voice + output schema + 1 good + 1 bad few-shot) | Selected KeyIssues with full article bundles (no scores) | Yes (`ephemeral`) | `LLMBriefing` JSON (no scores, no source URLs) |

Both prefixes clear the 1024-token minimum for Anthropic caching with comfortable margin. Day-over-day cache behavior is server-defined; AC10b acknowledges this.

---

## 5. Selection / Ranking Logic (revised)

### 5.1 Pre-clustering (Python, same-language only)

Token-overlap single-linkage as in v1 §5.1, threshold 75, 72h window, per category. Only same-language within a candidate cluster. Brand-overlap safety net for Fashion/Beauty unchanged.

### 5.2 Cross-language clustering (Call A)

Delegated to Haiku. Python's `rapidfuzz` cannot bridge "숏폼 화장품 리뷰" ≈ "short-form beauty reviews"; Haiku does this trivially. Output is authoritative; Python accepts Call A's cluster membership decisions.

### 5.3 Scoring (Python, post Call A)

Recompute on merged clusters:

- `diffusion_score = 0.6 * min(n_sources / 5, 1.0) + 0.4 * source_type_diversity`
- `novelty_score = max(0, 1 - 0.15 * prior_day_hits_last_7d)` where `prior_day_hits_last_7d` counts days in the last 7 where the primary entity appeared in `entity_history` (ingested from all articles, not just selected).
- **Warmup rule:**
  - If `min(entity_history.first_seen_at) > today - 7d` for the DB as a whole: `combined = 0.3 * novelty + 0.7 * diffusion`.
  - Else (steady state): `combined = 0.55 * novelty + 0.45 * diffusion`.
- **Day-1 behavior:** on the very first run, `entity_history` starts empty, so every entity is new; warmup weighting forces diffusion-led selection. This is the documented, intentional behavior.

### 5.4 Picking

1. Sort clusters per category by `combined_score` desc.
2. Take top `MAX_PER_CAT=3`, target `MIN_PER_CAT=2`.
3. Categories with <2 clusters at threshold do NOT placeholder or drop → their top remaining items flow into `misc_observations_ko` ("기타 관찰"), capped at 3 items total across the misc bucket.
4. Global cap: 13 items across sections + misc bucket.

**OQ4 resolved in this plan:** slow-news-day categories aggregate into "기타 관찰" (resolved, no longer open).

---

## 6. News Source List

**Unchanged from v1 §6.** Full YAML list reproduced in v1; v2 does not duplicate. Two adds pending researcher verification: `foodnavigator.com/rss` and `cosmeticsbusiness.com/rss`. Google News RSS query pattern identical. Redirect unwrap added per Step 3.

---

## 7. Testable Acceptance Criteria (revised)

| # | Criterion | Verification |
|---|---|---|
| AC1 | `python morning_brief.py dry-run` exits 0 in <30s on fixtures with zero network calls | CI: `DRY_RUN=1 pytest tests/test_end_to_end_dry_run.py -q` |
| AC2 | `.eml` contains exactly 5 category section headers (or a subset + "기타 관찰") | Regex match on rendered HTML |
| AC3 | `exec_summary_ko` has exactly 3 lines; `insight_box_ko` non-empty | pydantic-enforced; e2e test asserts count=3 |
| AC4 | Each rendered category section has 2–3 items; total items across sections+misc ≤ 13 | Unit test on selector.picker; e2e test asserts rendered item count |
| AC5 | Every item has ≥1 source URL as clickable link in the HTML body | Parse `.eml`, assert `<a href="http` count ≥ item count |
| AC6 | Body text is Korean (Hangul ratio ≥ 80% excluding URLs/source names) | Unicode ratio check |
| AC7 | Live run completes in <10 minutes end-to-end | `runs.run_duration_seconds < 600` |
| AC8 | Cross-lingual near-duplicate titles (e.g. "Zara launches X" + "자라, X 출시") end up in the SAME final cluster after Call A | Fixture test: Call A mock returns merged cluster; live smoke test on one real pair |
| AC9 | A story whose primary entity appeared in the last 7 days gets a lower `novelty_score` than a genuinely new story. `entity_history` ingests from ALL collected articles, not just selected KeyIssues | `test_selector.py` seeds `entity_history` + synthetic articles; warmup case explicitly tested |
| **AC10a** | Every live run's request payload includes `cache_control: {"type":"ephemeral"}` on the system block for both Call A and Call B | Deterministic: `test_summarizer.py` asserts on the request dict |
| **AC10b** | Two consecutive live runs within 5 minutes show `cache_read_input_tokens > 0` in Call A's usage (and ideally Call B's) | Manual live test, best-effort; acknowledges server-side variability |
| AC11 | `.eml` opens cleanly in at least one of Outlook / Apple Mail / Thunderbird with all links clickable | Manual one-time check |
| AC12 | If <3 feeds return articles, the script aborts with a clear error BEFORE any LLM call | `test_collector.py` mocks all feeds failing; asserts SystemExit and zero LLM invocations |
| AC13 | `rerender <run_id>` regenerates `.eml` from persisted Call B response + KeyIssue snapshot with zero API calls | e2e test |
| **AC14** | Renderer displays Python-computed scores (novelty/diffusion/combined), not LLM-written numbers. `LLMBriefing` schema contains no numeric score fields | Unit test: attempt to inject a fake score number into a Call B fixture response → pydantic rejects |
| **AC15** | Per-stage durations logged to `runs.stage_durations_json`; no single stage exceeds 50% of the total run budget | Assertion in e2e test; budget table below |

### Per-stage performance budgets (for a live `run` on typical daily load)

| Stage | Target | Hard cap | Rationale |
|---|---|---|---|
| collect | 60s | 180s | Bounded by per-host 1req/s + RSS count (~15 feeds) + enrichment on top-40 |
| select | 2s | 10s | Pure Python on a few hundred articles |
| call_a | 15s | 45s | Haiku, ~2500 input tokens, ~800 output tokens |
| call_b | 45s | 120s | Sonnet, ~2800 input tokens, ~1500 output tokens |
| render | 1s | 5s | Jinja2 + stdlib `email` |
| **total** | **~2 min** | **<10 min** (AC7) | |

No single stage budget is allowed to exceed 50% of the total hard cap (AC15 assertion: `max(stage_durations) / total_duration < 0.5`).

---

## 8. ADR (revised)

**Decision:** Build a local Python 3.11+ CLI (`python morning_brief.py`) that collects via RSS (with entity ingest from every article), pre-clusters same-language duplicates with `rapidfuzz`, scores novelty (7-day warmup aware) + diffusion in Python, calls **Haiku (Call A)** to re-cluster across languages and canonicalize, recomputes scores in Python on merged clusters, then calls **Sonnet (Call B)** to write a Korean briefing whose JSON contains no numeric scores. The renderer injects Python-computed scores into the HTML and builds a `.eml` file. SQLite holds cross-day state including `entity_history`.

**Drivers:**
- Korean output quality → Sonnet 4.6 for Call B.
- Cross-lingual clustering satisfying AC8 → LLM-based re-cluster (Haiku).
- Editorial transparency (Principle 3) → Python-authoritative scores, LLM never writes numbers.
- Cache friendliness across daily runs → stable system prefixes for both calls.

**Alternatives considered:**
- **Single-call pipeline (v1 proposal)** — rejected: (a) `rapidfuzz`-only clustering demonstrably fails on cross-lingual pairs, breaking AC8 as specified; (b) single LLM call conflates 5 concerns with opaque failure modes; (c) LLM-written score numbers cannot be bit-exactly verified against scorer.py, violating Principle 3.
- **Three-call pipeline (cluster → rank → write)** — rejected: ranking is deterministic Python, so a dedicated LLM call adds latency without quality gain.
- **Embedding-based clustering instead of Call A** — deferred: adds an API or local model dep; LLM re-clustering via Haiku is cheaper for MVP and has the side benefit of canonicalizing the entity label.
- **GPT-4.1 / Gemini 2.5 Pro** — rejected for Korean fluency / caching control reasons (see v1 §1 D1, unchanged).
- **Gmail API Phase-1 delivery** — deferred (see v1 §1 D2).
- **JSON-file storage** — rejected (see v1 §1 D4).

**Why chosen:** Two-call pipeline is the minimum structural change that makes each of AC3 / AC8 / AC9 / AC14 (new) independently satisfiable and testable. Python ownership of scores makes Principle 3 bit-exact. Collapsed 6-module structure keeps the code surface small enough for a 1–2 day MVP.

**Consequences:**
- (+) Cross-lingual duplicates actually merge (AC8 passes by design, not by luck).
- (+) Score numbers in the final email are deterministic and reproducible from SQLite state.
- (+) Day-over-day cache wins are real for Call A, not just within 5-min dev windows.
- (+) Each pipeline stage is debuggable in isolation; persisted JSON per call supports `rerender` + targeted retries.
- (−) Two round-trips instead of one (~2–4 extra seconds); well inside the 10-min budget.
- (−) Two prompts to maintain (mitigated: both are stable content in `prompts/`).
- (−) Day-1 briefing is diffusion-weighted by design (warmup). User sees some low-signal stories the first morning; stabilizes after 7 days. Documented.

**Follow-ups:**
- FU1: Measure first-week Call A accuracy on cross-lingual pairs. If recall is low, escalate Call A model from Haiku to Sonnet (one-line config change).
- FU2: Gmail Drafts delivery (Phase 2).
- FU3: Embedding-based clustering as a Call A replacement if LLM latency becomes an issue.
- FU4: Windows Task Scheduler template.
- FU5: Expand `config/brands.txt` from first-week error analysis.
- FU6: Consider merging `call_a_system.md` and `call_b_system.md` into a single shared glossary block for double-cache reuse (micro-optimization).

---

## 9. Implementation Phases

### Phase 1 — MVP vertical slice (1–2 days)
**Goal:** user runs one command, gets a reviewable Korean `.eml` in `out/`, in <10 minutes of wall-clock time.
- Steps 1–8 from §3.
- AC1–AC15 all passing (AC10b is best-effort; rest are automated or one-time manual).
- Windows 11 + Git Bash primary target.

### Phase 2 — Polish (post-MVP)
- Gmail Drafts delivery (`delivery/gmail_draft.py` — even though v2 collapsed modules, Phase 2 may reintroduce a `delivery/` folder if warranted).
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

OQ4 is now **resolved** (misc "기타 관찰" bucket). The remaining open items carry over from v1:

- [ ] OQ1: Subject-line A/B variants vs single canonical form (dynamic join already specified)
- [ ] OQ2: Seed `config/brands.txt` with ~50 brands vs ship empty
- [ ] OQ3: Time zone for `generated_at` — KST fixed (proposed) vs local
- [ ] OQ5: Provider abstraction day-1 vs Anthropic-only for Phase 1

One new item introduced by v2 design:

- [ ] OQ6: Call A model — default Haiku 4. Escalation criterion: if AC8 live recall on cross-lingual pairs is <80% after first week, switch to Sonnet. Confirm user is OK with this auto-escalation policy or wants to stay on Haiku unconditionally for cost.

---

## Pushbacks / Notes to Critic

Architect review was adopted almost wholesale. Three minor pushbacks for the Critic to arbitrate:

1. **"6 modules max"** — interpreted as 6 top-level Python code modules. Two markdown prompt files plus one Jinja2 template file live in content folders, not counted as modules. This matches the spirit (collapse sprawl) without forcing prompts-as-code.
2. **`rich` removed** — complied. Minor UX regression on Windows terminals (no clickable paths); acceptable given dep-count concerns.
3. **Call A = Haiku** — adopted as default, but added FU1 escalation path to Sonnet if cross-lingual recall is inadequate. One-line config change, ring-fenced risk.

All other synthesis proposals adopted without pushback.
