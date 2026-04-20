# Morning Consumer Trend Briefing — Plan v1

**Source spec:** `.omc/specs/deep-interview-morning-consumer-trend-briefing.md` (ambiguity 19.5%, PASSED)
**Plan type:** RALPLAN-DR consensus plan (pre-Architect/Critic review)
**Target:** Local Python 3.11+ CLI, Windows 11 primary, Git Bash shell
**Scope:** MVP end-to-end vertical slice, 1–2 days of focused work

---

## 1. RALPLAN-DR Summary

### Principles (5)
1. **Simplicity over automation** — MVP is one `python morning_brief.py` invocation. No scheduler, no daemon, no web UI. Automation is a Phase 2 wrapper.
2. **LLM does translation + summarization in one pass** — no separate translator; Korean output is produced directly by the summarizer from mixed ko/en input.
3. **Editorial transparency** — every `KeyIssue` in the draft carries its selection score (novelty + diffusion) and source article list so the human reviewer can trust-but-verify in ≤10 minutes.
4. **Cache-hit-friendly prompt shape** — stable category definitions, editorial guidelines, and output schema live in a large prefix (>1024 tokens) that is reused every run; only the daily article bundle varies.
5. **Reversible storage** — all intermediate artifacts (raw articles, dedup groups, LLM JSON, `.eml`) are written to disk so any single stage can be re-run without re-fetching.

### Decision Drivers (top 3)
1. **Korean output quality** — the user reads and forwards this to Korean-speaking clients; bad Korean = the whole product fails.
2. **Fast time-to-first-valuable-output** — target: user gets a reviewable draft on Day 2 of work, not Day 10.
3. **Low, predictable operating cost** — single laptop, prompt caching mandatory, no per-user infra.

### Viable Options per Key Decision

#### D1. LLM choice

| Option | Pros | Cons |
|---|---|---|
| **Claude Sonnet 4.6** (chosen) | Strong Korean fluency, native prompt caching (5min + 1h TTL), `anthropic` SDK mature, JSON mode via tool-use reliable | Single-vendor lock; cost slightly above GPT-4.1-mini |
| GPT-4.1 | Cheaper at equivalent tier; broad ecosystem | Prompt caching is implicit/automatic (less controllable); Korean nuance marginally weaker in long-form summaries |
| Gemini 2.5 Pro | Large context, cheap caching | Korean output occasionally over-translates idioms; SDK less stable; JSON schema adherence weaker |

**Choice: Claude Sonnet 4.6** with explicit `cache_control` breakpoints. Swappable via a single `LLM_PROVIDER` env var — abstraction lives in `summarizer/llm_client.py`.

#### D2. Email delivery mechanism

| Option | Pros | Cons |
|---|---|---|
| **`.eml` file on disk** (chosen for Phase 1) | Zero auth, zero network, zero rate-limit; user double-clicks → opens in default client → edit → send | User must manually attach recipients if not pre-filled; no "Drafts folder" affordance |
| Gmail API draft | Lands in Gmail Drafts, mobile-accessible, matches the "검토 후 발송" flow cleanly | OAuth setup is a 15-min detour on first run; requires Google Cloud project; fails if user uses non-Gmail |
| Clipboard / console print | Trivially simple | Breaks HTML formatting; loses embedded links; defeats the "copy-paste 최소화" acceptance criterion |

**Choice: `.eml` file for Phase 1**, with `delivery/gmail_draft.py` stub reserved for Phase 2. Rationale: the acceptance criterion says "`.eml` 파일 생성 또는 Gmail 임시 저장함" — `.eml` is the faster path and works offline.

#### D3. News collection method

| Option | Pros | Cons |
|---|---|---|
| **RSS-first + targeted oEmbed/meta scraping for top-N only** (chosen) | RSS is stable, cheap, paywall-safe. Only scrape the ~20–30 articles that pass initial filtering — bounds legal/rate-limit exposure | Some premium sources (BoF, Vogue Business) gate full text behind paywall; we get headline+deck only |
| RSS only | Simplest; no scraping concerns | Many RSS feeds truncate to 1–2 sentences; summarizer has less signal |
| Full scraping (requests+BeautifulSoup on every article) | Full body text → best summaries | Fragile selectors per domain; ToS risk; slow; blocks common |

**Choice: RSS-first with opportunistic OpenGraph/meta-description enrichment** via `requests` + `BeautifulSoup`, capped at top-N articles post-ranking. Paywalled sources contribute headline+deck only — explicitly marked in the draft.

#### D4. Storage

| Option | Pros | Cons |
|---|---|---|
| **SQLite** (chosen) | Single-file, stdlib (`sqlite3`), supports dedup lookups across days ("was this story in yesterday's briefing?"), trivial to query | Slightly more boilerplate than JSON |
| JSON files per run | Dead-simple; human-readable | Cross-day dedup requires loading N files; no indexing |
| In-memory only | Zero setup | Cannot detect "this story ran yesterday too" → defeats novelty scoring |

**Choice: SQLite** at `.omc/state/briefing/briefing.db`. Cross-day novelty check (an article's core entity appearing in the last 7 days reduces its novelty score) is a core feature, not an add-on.

---

## 2. Architecture

### 2.1 Data flow (prose)

```
           ┌──────────────┐
           │ sources.yml  │  (curated feed list, per category)
           └──────┬───────┘
                  │
      ┌───────────▼────────────┐
      │  collector/            │  feedparser → raw Article[]
      │  - rss_fetcher.py      │  (dedup by canonical URL in SQLite)
      │  - enricher.py         │  OpenGraph meta fetch for top candidates
      └───────────┬────────────┘
                  │  Article[]  (persisted to SQLite: articles table)
                  ▼
      ┌────────────────────────┐
      │  selector/             │  novelty + diffusion scoring
      │  - clusterer.py        │  group near-duplicate stories across sources
      │  - scorer.py           │  score each cluster
      │  - picker.py           │  top-N per category + overall cap
      └───────────┬────────────┘
                  │  KeyIssue[]  (a cluster with score + member articles)
                  ▼
      ┌────────────────────────┐
      │  summarizer/            │  Claude Sonnet 4.6, one call per run
      │  - prompt_builder.py    │  builds cache-friendly prefix + payload
      │  - llm_client.py        │  anthropic SDK + cache_control
      │  - schema.py            │  pydantic models for LLM JSON output
      └───────────┬────────────┘
                  │  Briefing (exec_summary + 5 sections + insight_box)
                  ▼
      ┌────────────────────────┐
      │  renderer/              │  Jinja2 HTML template → body
      │  - html_template.j2     │
      │  - eml_builder.py       │  email.message.EmailMessage → .eml
      └───────────┬────────────┘
                  │  briefing_YYYY-MM-DD.eml
                  ▼
      ┌────────────────────────┐
      │  delivery/              │  write .eml to out/, print path to stdout
      │  - file_writer.py       │  (Phase 2: gmail_draft.py)
      └────────────────────────┘
```

### 2.2 File / directory structure

```
morning_brief/
├── pyproject.toml                 # PEP 621, Python 3.11+, deps pinned
├── README.md                      # Windows + Git Bash setup, .env.example
├── .env.example                   # ANTHROPIC_API_KEY, BRIEF_SENDER, BRIEF_RECIPIENTS
├── morning_brief.py               # CLI entry (argparse): run / dry-run / re-render
├── config/
│   ├── sources.yml                # RSS feeds per category (see §6)
│   ├── categories.yml             # 5 categories with ko/en keywords + exclusions
│   └── editorial.md               # editorial voice guide (goes into cached prefix)
├── morning_brief/
│   ├── __init__.py
│   ├── models.py                  # pydantic: Article, Cluster, KeyIssue, Briefing
│   ├── db.py                      # SQLite bootstrap + dao helpers
│   ├── collector/
│   │   ├── __init__.py
│   │   ├── rss_fetcher.py
│   │   └── enricher.py
│   ├── selector/
│   │   ├── __init__.py
│   │   ├── clusterer.py
│   │   ├── scorer.py
│   │   └── picker.py
│   ├── summarizer/
│   │   ├── __init__.py
│   │   ├── llm_client.py          # anthropic SDK wrapper w/ cache_control
│   │   ├── prompt_builder.py
│   │   ├── prompts/
│   │   │   ├── system_prefix.md   # stable, cached (>1024 tokens)
│   │   │   └── user_template.md   # per-run article bundle
│   │   └── schema.py              # pydantic models matching LLM JSON
│   ├── renderer/
│   │   ├── __init__.py
│   │   ├── templates/
│   │   │   └── briefing.html.j2
│   │   └── eml_builder.py
│   └── delivery/
│       ├── __init__.py
│       └── file_writer.py
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── sample_rss.xml
│   │   ├── sample_articles.json
│   │   └── mock_llm_response.json
│   ├── test_clusterer.py
│   ├── test_scorer.py
│   ├── test_prompt_builder.py
│   ├── test_renderer.py
│   └── test_end_to_end_dry_run.py
└── out/                           # .eml files + per-run debug artifacts
    └── .gitkeep
```

State lives under `.omc/state/briefing/` (`briefing.db`, debug JSON dumps). The package itself lives under a `morning_brief/` subfolder of the project root.

### 2.3 Key data schemas (pydantic)

```python
# morning_brief/models.py  (illustrative — not code to write now)

class Article:
    id: str                    # sha1(canonical_url)
    title: str
    source_name: str
    source_type: Literal["TraditionalMedia", "SpecializedMedia", "CuratedTrendReport"]
    url: str
    canonical_url: str
    language: Literal["ko", "en"]
    published_at: datetime     # UTC
    category: Literal["Food","Beauty","Fashion","Living","Hospitality"] | None
    raw_summary: str           # from RSS description
    enriched_text: str | None  # from OpenGraph/meta (top-N only)
    fetched_at: datetime

class Cluster:                 # group of articles telling the same story
    id: str
    category: str
    article_ids: list[str]
    representative_title: str
    diffusion_score: float     # 0..1, based on count + source diversity
    novelty_score: float       # 0..1, based on entity-recency vs 7-day window
    combined_score: float      # weighted sum, see §5

class KeyIssue:                # a Cluster after selection, ready for LLM
    cluster_id: str
    category: str
    score: float
    article_bundle: list[Article]   # capped at 5 per cluster into prompt

class Briefing:
    generated_at: datetime
    exec_summary_ko: list[str]      # exactly 3 lines
    sections: dict[str, list[BriefingItem]]   # category → 2-3 items
    insight_box_ko: str
    meta: dict                      # run stats, token usage, cache hits

class BriefingItem:
    title_ko: str
    summary_ko: str                 # 1-3 sentences
    source_urls: list[str]
    source_names: list[str]
    score: float
    is_paywalled: bool              # flag when only headline+deck available
```

---

## 3. Concrete Implementation Steps (ordered, file-level)

Each step lists **file**, **purpose**, **depends-on**. All are part of Phase 1 (MVP).

### Step 1 — Project scaffold & config
- `pyproject.toml` — declare deps: `feedparser>=6.0`, `httpx>=0.27`, `beautifulsoup4>=4.12`, `pydantic>=2.6`, `jinja2>=3.1`, `pyyaml>=6.0`, `anthropic>=0.40`, `python-dotenv>=1.0`, `rapidfuzz>=3.6`, `rich>=13.0`. Dev: `pytest`, `pytest-mock`.
- `.env.example` — `ANTHROPIC_API_KEY=`, `BRIEF_SENDER="Me <me@example.com>"`, `BRIEF_RECIPIENTS="a@x.com,b@x.com"`, `LLM_MODEL=claude-sonnet-4-6`, `DRY_RUN=0`.
- `config/categories.yml` — 5 categories with ko/en keyword seeds and exclusion terms (e.g. exclude "정치", "스포츠" for disambiguation).
- `config/sources.yml` — see §6 for concrete URLs.
- `config/editorial.md` — Korean editorial voice guide (goes into cached prefix).
- **Depends on:** nothing.

### Step 2 — Data layer
- `morning_brief/models.py` — pydantic models from §2.3.
- `morning_brief/db.py` — SQLite schema: `articles`, `clusters`, `cluster_members`, `runs`, `entity_history` (for novelty lookup). Idempotent `bootstrap()`.
- **Depends on:** Step 1.

### Step 3 — Collector
- `morning_brief/collector/rss_fetcher.py` — iterate `sources.yml`, `feedparser.parse` with `httpx` for fetching (so we control timeouts + user-agent). Deduplicate within-run by canonical URL. Assign category from source metadata first, fall back to keyword match on title+summary.
- `morning_brief/collector/enricher.py` — for a given list of `Article`, fetch HTML with `httpx` (timeout 8s, 3 retries, polite 1 req/sec per host), parse `<meta property="og:description">` and first `<p>` as `enriched_text`. Skip if paywall markers detected (e.g. response < 2KB, "subscribe" in title class).
- **Depends on:** Step 2.
- **Acceptance:** Given `tests/fixtures/sample_rss.xml` as a local file, `rss_fetcher` returns ≥5 `Article` instances with correct categories.

### Step 4 — Selector (clustering + scoring + picking)
- `morning_brief/selector/clusterer.py` — cluster articles by title similarity using `rapidfuzz.fuzz.token_set_ratio` ≥ 75 as pair-wise threshold; single-linkage on same-category articles within a 72-hour window. Output `Cluster[]`. (Details in §5.)
- `morning_brief/selector/scorer.py` — compute `diffusion_score` (source count + source-type diversity) and `novelty_score` (inverse of entity recency, where entities = extracted proper nouns via a simple NER-lite regex + category keyword hits) and `combined_score = 0.55 * novelty + 0.45 * diffusion`.
- `morning_brief/selector/picker.py` — pick per category: 2–3 top-scoring clusters (configurable `MIN_PER_CAT=2`, `MAX_PER_CAT=3`); cap total at 13 to keep the prompt bundle bounded.
- **Depends on:** Step 3.
- **Acceptance:** Unit tests with synthetic article sets prove clustering merges obvious duplicates and scorer prefers stories with higher source diversity.

### Step 5 — Summarizer (prompts + LLM call)
- `morning_brief/summarizer/prompts/system_prefix.md` — cache-friendly prefix (see §4). Must exceed 1024 tokens for Sonnet caching to engage.
- `morning_brief/summarizer/prompts/user_template.md` — Jinja2 skeleton that embeds per-run article bundles (title, source, published_at, language, raw_summary, enriched_text, URL).
- `morning_brief/summarizer/schema.py` — pydantic `LLMBriefing` matching the JSON schema in §4.3.
- `morning_brief/summarizer/prompt_builder.py` — assembles the two-message pattern: `system` (cached, stable), `user` (per-run). Uses `anthropic`'s `cache_control: {"type":"ephemeral"}` on the system block.
- `morning_brief/summarizer/llm_client.py` — thin wrapper: `summarize(key_issues) -> LLMBriefing`. Logs `usage.cache_creation_input_tokens` + `usage.cache_read_input_tokens`. Retries once on JSON parse failure with a tightening follow-up. Honours `DRY_RUN=1` by returning a fixture response.
- **Depends on:** Step 4.
- **Acceptance:** `DRY_RUN=1` path produces a valid `Briefing` from fixtures with zero API calls. Live call path produces the same shape.

### Step 6 — Renderer + delivery
- `morning_brief/renderer/templates/briefing.html.j2` — inlined-CSS HTML: exec summary (3 lines, large font), 5 category sections (emoji per category is OK for skim, e.g. 🍽🧴👗🏠🏨 optional), each item = title + 1–3 sentence ko summary + source links (max 3) + score pill; insight box at bottom.
- `morning_brief/renderer/eml_builder.py` — build `email.message.EmailMessage` with multipart/alternative (plain + HTML); set `Subject`, `From`, `To` from env; write to `out/briefing_YYYY-MM-DD.eml`.
- `morning_brief/delivery/file_writer.py` — write the .eml and print absolute path to stdout via `rich.console.Console` for clickable terminal.
- **Depends on:** Step 5.
- **Acceptance:** Opening the `.eml` in Outlook/Thunderbird/Apple Mail renders the briefing legibly, preserves all source hyperlinks, and subject line is `"[소비재 트렌드 조간] YYYY-MM-DD (Food/Beauty/Fashion/Living/Hospitality)"`.

### Step 7 — CLI + end-to-end wiring
- `morning_brief.py` at repo root — argparse subcommands:
  - `run` — full pipeline.
  - `dry-run` — same pipeline with `DRY_RUN=1` (mocked LLM, still writes real .eml).
  - `rerender <run_id>` — re-run renderer from persisted LLM output (fast edit loop).
  - `--limit-per-cat N` override.
- Pipeline writes debug artifacts under `.omc/state/briefing/runs/<YYYY-MM-DD-HHMM>/` (raw articles JSON, clusters JSON, llm_request.json, llm_response.json).
- **Depends on:** Step 6.
- **Acceptance:** `python morning_brief.py dry-run` completes in < 30 seconds on fixture data and produces a valid `.eml`.

### Step 8 — Tests + smoke validation
- `tests/test_end_to_end_dry_run.py` — uses fixture RSS + fixture LLM response, asserts `.eml` file is created, contains all 5 category headings, exec summary has exactly 3 lines, and every item has at least one source URL.
- `tests/test_clusterer.py`, `test_scorer.py`, `test_prompt_builder.py`, `test_renderer.py` — unit tests.
- README with Windows/Git Bash setup: `python -m venv .venv`, `source .venv/Scripts/activate`, `pip install -e .`, `cp .env.example .env`, `python morning_brief.py dry-run`, then `python morning_brief.py run`.
- **Depends on:** Step 7.
- **Acceptance:** `pytest` runs green locally with zero network calls.

---

## 4. Prompt Engineering

### 4.1 Two-message cache-friendly shape

```
system  [CACHED, ephemeral breakpoint]
├── Role: "You are a Korean consumer-trend editor..."
├── Editorial voice guide (from config/editorial.md)
├── 5 category definitions + examples (Food/Beauty/Fashion/Living/Hospitality)
├── Selection philosophy: novelty vs diffusion explained
├── Output contract (JSON schema, field-by-field)
├── Translation guidelines (brand names, jargon, 존칭)
├── Forbidden patterns (no emojis in body, no "이 뉴스는...", etc.)
└── Few-shot examples: 1 good briefing, 1 bad briefing
   → total target: 1500–2500 tokens (safely above 1024)

user  [NOT cached, per-run]
├── Today's date (ko: 2026-04-18)
├── Run meta: N clusters selected, scoring window
└── For each cluster (category-grouped):
    ├── cluster_id, category, combined_score, novelty, diffusion
    ├── Representative title
    ├── Member articles: [source, lang, published_at, title, raw_summary, enriched_text, url]
    └── Paywall flag per article
```

### 4.2 Caching strategy
- Single `cache_control: {"type":"ephemeral"}` on the **system block**. Claude caches the system prefix for 5 minutes by default (1-hour beta available if token count warrants).
- The system prefix must change **only** when `config/editorial.md` or `config/categories.yml` changes. A `prefix_hash` is recorded per run; hash mismatch invalidates cache.
- Expected per-run usage: cold run creates cache (`cache_creation_input_tokens` ≈ prefix size); subsequent runs within 5 minutes hit `cache_read_input_tokens`. **Primary win is during dev iteration**, not day-over-day (runs are 24h apart).
- Cost note: Because runs are daily, cache is effectively cold every morning. The *real* cache benefit is during `dry-run` / `rerender` iteration while tuning. This is acceptable — we still design for cache even if first-of-day is always a miss.

### 4.3 Output JSON schema (what the LLM must return)

```json
{
  "exec_summary_ko": ["line1", "line2", "line3"],
  "sections": {
    "Food": [
      {
        "title_ko": "...",
        "summary_ko": "... 1-3 sentences ...",
        "source_urls": ["https://...", "..."],
        "source_names": ["BoF", "조선일보"],
        "why_selected": "novelty=0.82 / diffusion=0.71",
        "is_paywalled": false
      }
    ],
    "Beauty": [...],
    "Fashion": [...],
    "Living": [...],
    "Hospitality": [...]
  },
  "insight_box_ko": "해당일 전반 트렌드에 대한 2-4 문장 에디터 코멘트."
}
```

Enforcement: request via Anthropic tool-use with a strict JSON tool schema, or instruct "respond with JSON only" + validate with pydantic in `llm_client.py`. On parse failure, send one retry with the parse error appended to the user message. If retry fails, surface a clear CLI error and persist the raw response.

---

## 5. Selection / Ranking Logic

### 5.1 Clustering (same story across sources)

1. **Candidate pairs**: all articles within same category, published within 72 hours of each other.
2. **Pairwise similarity** using `rapidfuzz.fuzz.token_set_ratio(title_a, title_b)` on *normalized* titles (strip punctuation, lowercase, Korean postpositions trimmed via a small list: `은/는/이/가/을/를/의/에/와/과`).
3. **Threshold**: pair is "same story" if ratio ≥ 75. Rationale: tuned low enough to merge translated headlines ("Zara launches X" ↔ "자라, X 출시"), high enough to avoid merging unrelated stories.
4. **Optional safety net**: if category is Fashion/Beauty, also check brand-name token overlap — if both titles share a known brand token (from a small brand dict in `config/brands.txt`) and ratio ≥ 65, cluster them.
5. **Single-linkage clustering** via union-find: any pair above threshold joins their clusters.
6. Each cluster stores `representative_title` = title of the article from the most reputable source (source-tier ranking defined in `sources.yml`).

**Why not embeddings?** Adds an extra API dependency (or local sentence-transformers model — slow cold start on Windows). Token-overlap + brand-dict fallback hits the quality bar for MVP; embeddings are a Phase 2 upgrade (`test_clusterer.py` will make the swap cheap).

### 5.2 Scoring

- **`diffusion_score`** (0..1):
  ```
  raw = 0.6 * min(n_sources / 5, 1.0) + 0.4 * source_type_diversity
  where source_type_diversity ∈ {0, 0.5, 1.0} for {1, 2, 3} distinct source_types.
  ```
  A story covered by 3+ sources spanning both domestic and specialized media gets ~1.0.

- **`novelty_score`** (0..1):
  - Extract "entities" from the cluster's titles: proper nouns (regex: sequences matching `[A-Z][A-Za-z]+` for English; Korean brand/product tokens from `config/brands.txt`).
  - Query `entity_history` table (SQLite) for the last 7 days.
  - `novelty = max(0, 1 - 0.15 * prior_day_hits)` — a story whose key entity hasn't appeared in 7 days scores 1.0; one that appeared every day for a week scores ~0.0.
  - Entity extraction is intentionally dumb-but-fast. Phase 2 can upgrade to a Korean NER model.

- **`combined_score = 0.55 * novelty + 0.45 * diffusion`**
  - Weight bias toward novelty reflects the spec's "새로운 트렌드·변화의 등장" phrasing listed first in acceptance criteria.
  - Weights exposed as constants in `scorer.py` for easy tuning.

### 5.3 Picking

1. Within each category, sort clusters by `combined_score` desc.
2. Take top `MAX_PER_CAT=3`, enforce `MIN_PER_CAT=2` (if fewer than 2 clusters exist, fall back to top individual articles — rare, but log a warning).
3. Enforce global cap: total across all categories ≤ 13.
4. Produce final `KeyIssue[]` sent to the summarizer.

---

## 6. News Source List (concrete URLs)

Stored in `config/sources.yml`. `lang`, `tier`, and `type` drive scoring/diversity.

```yaml
# Global specialized media (English, SpecializedMedia)
- name: "Business of Fashion"
  url: "https://www.businessoffashion.com/arc/outboundfeeds/rss/"
  lang: en
  tier: 1
  type: SpecializedMedia
  categories: [Fashion, Beauty]
  paywall: partial

- name: "WWD"
  url: "https://wwd.com/feed/"
  lang: en
  tier: 1
  type: SpecializedMedia
  categories: [Fashion, Beauty]
  paywall: partial

- name: "Vogue Business"
  url: "https://www.voguebusiness.com/feed"
  lang: en
  tier: 1
  type: SpecializedMedia
  categories: [Fashion, Beauty]
  paywall: partial

- name: "Retail Dive"
  url: "https://www.retaildive.com/feeds/news/"
  lang: en
  tier: 2
  type: SpecializedMedia
  categories: [Food, Beauty, Fashion, Living]

- name: "Skift"
  url: "https://skift.com/feed/"
  lang: en
  tier: 1
  type: SpecializedMedia
  categories: [Hospitality]

- name: "Hospitality Net"
  url: "https://www.hospitalitynet.org/rss/news.xml"
  lang: en
  tier: 2
  type: SpecializedMedia
  categories: [Hospitality]

- name: "Food Dive"
  url: "https://www.fooddive.com/feeds/news/"
  lang: en
  tier: 2
  type: SpecializedMedia
  categories: [Food]

# Curated trend reports (CuratedTrendReport)
- name: "TrendWatching Insights"
  url: "https://www.trendwatching.com/rss"
  lang: en
  tier: 1
  type: CuratedTrendReport
  categories: [Food, Beauty, Fashion, Living, Hospitality]

- name: "Springwise"
  url: "https://www.springwise.com/feed/"
  lang: en
  tier: 2
  type: CuratedTrendReport
  categories: [Food, Beauty, Fashion, Living, Hospitality]

# Google News RSS per category (ko + en queries)
- name: "Google News KR — Food"
  url: "https://news.google.com/rss/search?q=%EC%8B%9D%ED%92%88+%EC%86%8C%EB%B9%84%EC%9E%90+%ED%8A%B8%EB%A0%8C%EB%93%9C&hl=ko&gl=KR&ceid=KR:ko"
  lang: ko
  tier: 2
  type: TraditionalMedia
  categories: [Food]

- name: "Google News KR — Beauty"
  url: "https://news.google.com/rss/search?q=%EB%B7%B0%ED%8B%B0+%ED%99%94%EC%9E%A5%ED%92%88+%ED%8A%B8%EB%A0%8C%EB%93%9C&hl=ko&gl=KR&ceid=KR:ko"
  lang: ko
  tier: 2
  type: TraditionalMedia
  categories: [Beauty]

- name: "Google News KR — Fashion"
  url: "https://news.google.com/rss/search?q=%ED%8C%A8%EC%85%98+%EB%B8%8C%EB%9E%9C%EB%93%9C+%EC%86%8C%EB%B9%84%EC%9E%90&hl=ko&gl=KR&ceid=KR:ko"
  lang: ko
  tier: 2
  type: TraditionalMedia
  categories: [Fashion]

- name: "Google News KR — Living"
  url: "https://news.google.com/rss/search?q=%EB%9D%BC%EC%9D%B4%ED%94%84%EC%8A%A4%ED%83%80%EC%9D%BC+%EC%86%8C%EB%B9%84%EC%9E%90+%ED%8A%B8%EB%A0%8C%EB%93%9C&hl=ko&gl=KR&ceid=KR:ko"
  lang: ko
  tier: 2
  type: TraditionalMedia
  categories: [Living]

- name: "Google News KR — Hospitality"
  url: "https://news.google.com/rss/search?q=%ED%98%B8%ED%85%94+%EC%9D%B8%EB%B0%94%EC%9A%B4%EB%93%9C+%EC%86%8C%EB%B9%84%EC%9E%90&hl=ko&gl=KR&ceid=KR:ko"
  lang: ko
  tier: 2
  type: TraditionalMedia
  categories: [Hospitality]

- name: "Google News EN — Consumer Trends"
  url: "https://news.google.com/rss/search?q=consumer+trend+%22food%22+OR+%22beauty%22+OR+%22fashion%22+OR+%22hospitality%22&hl=en-US&gl=US&ceid=US:en"
  lang: en
  tier: 2
  type: TraditionalMedia
  categories: [Food, Beauty, Fashion, Living, Hospitality]
```

**Google News RSS query pattern** (documented in-file): `https://news.google.com/rss/search?q=<URL-encoded query>&hl=<lang>&gl=<country>&ceid=<country>:<lang>`. Keywords per category live in `config/categories.yml` so the user can tune without editing source URLs.

**Paywall policy:** feeds with `paywall: partial` contribute headline + feed-level summary only; `enricher.py` skips body fetch when `paywall: full`. The rendered item is flagged with a subtle `[요약본]` tag in the HTML.

**Fallback:** if an individual feed returns HTTP error or < 1 item, log a warning, continue. If < 3 total feeds succeed across the run, abort with a clear error before spending LLM tokens.

---

## 7. Testable Acceptance Criteria (inherited + sharpened)

Every item below is something Critic can mechanically verify.

| # | Criterion | Verification |
|---|---|---|
| AC1 | `python morning_brief.py dry-run` exits 0 in < 30s on fixture inputs with zero network calls | CI/local: `DRY_RUN=1 pytest tests/test_end_to_end_dry_run.py -q` |
| AC2 | Briefing `.eml` contains exactly 5 category section headers (Food/Beauty/Fashion/Living/Hospitality) | Test opens `.eml`, asserts regex matches for each category heading |
| AC3 | `exec_summary_ko` has **exactly 3** lines; `insight_box_ko` non-empty | LLM JSON validated by pydantic; end-to-end test asserts count=3 |
| AC4 | Each category section has 2–3 items; total items across all sections ≤ 13 | Unit test on `picker.py`; e2e test asserts rendered item count |
| AC5 | Every item has ≥ 1 source URL rendered as a clickable link in the HTML body | Parse `.eml`, assert `<a href="http` count ≥ item count |
| AC6 | Body text is Korean (source names/URLs may be English/Latin) | Unicode ratio check: >= 80% of non-URL, non-source-name chars in Hangul ranges |
| AC7 | Run in under 10 minutes end-to-end with live APIs (human-observed once, asserted via `run_duration_seconds` metric in `runs` table) | User runs `python morning_brief.py run`; `.omc/state/briefing/briefing.db` shows `run_duration_seconds < 600` |
| AC8 | When same story appears in ≥ 2 sources within the window, they end up in the same cluster | `test_clusterer.py` with synthetic near-duplicate titles |
| AC9 | Novelty scoring de-prioritizes a story whose entity appeared in the last 7 days | `test_scorer.py` with a synthetic entity_history row |
| AC10 | Prompt caching path is engaged: `usage.cache_read_input_tokens > 0` on the second consecutive live run within 5 minutes | Live test (manual or scripted): two runs in quick succession; inspect `runs.llm_usage_json` |
| AC11 | `.eml` opens cleanly in at least one of (Outlook, Apple Mail, Thunderbird) with all links clickable and HTML formatting preserved | Manual one-time check, screenshotted for the PR |
| AC12 | If fewer than 3 feeds return articles, the script aborts with a clear error **before** spending LLM tokens | `test_collector.py` mocks all feeds failing; asserts `SystemExit` and no LLM call |
| AC13 | `rerender <run_id>` regenerates `.eml` from persisted LLM JSON without any API call | e2e test |

### Smoke test (no API, no network)

```
# tests/fixtures/sample_articles.json  — 20 articles across 5 categories, including 3 near-duplicate pairs
# tests/fixtures/mock_llm_response.json — a valid LLMBriefing payload

pytest tests/test_end_to_end_dry_run.py
# must produce out/briefing_<TODAY>.eml with:
#  - 3-line exec summary
#  - 5 categories
#  - 10-13 items total
#  - insight box present
#  - 0 bytes sent to any network
```

---

## 8. ADR

**Decision:** Build a local Python 3.11+ CLI (`python morning_brief.py`) that collects via RSS, clusters/scores with lightweight heuristics, summarizes via Claude Sonnet 4.6 in one cache-friendly call, renders an HTML email, and writes a `.eml` file for the user to open and send. SQLite holds cross-day state. Gmail API path is stubbed for Phase 2.

**Drivers:**
- Korean output quality is the user-visible quality bar → Claude Sonnet 4.6 for its Korean summarization quality.
- 10-minute total runtime with human-in-the-loop → no scheduler, no queue, just a script.
- Predictable operating cost on a laptop → SQLite + RSS + single LLM call with prompt caching.

**Alternatives considered:**
- GPT-4.1 for LLM → rejected for marginally weaker Korean nuance in long-form summaries and less controllable caching.
- Gemini 2.5 Pro → rejected for weaker JSON-schema adherence and occasional Korean idiom over-translation.
- Gmail API for Phase 1 delivery → rejected: OAuth detour hurts time-to-first-value; non-Gmail users excluded.
- JSON-file storage → rejected: cross-day novelty lookup is core, not incidental.
- Full-text scraping on every article → rejected: fragile, ToS-risky, and RSS + opportunistic OpenGraph gives enough signal.
- Embedding-based clustering → deferred to Phase 2: adds a dep (API or local model) without commensurate MVP gain over `rapidfuzz` + brand dict.

**Why chosen:** The stack minimizes moving parts while directly targeting the acceptance criteria. Every deferred decision (Gmail API, embeddings, scheduler) has a clean upgrade path because of the module boundaries (`delivery/`, `selector/clusterer.py`, Phase 2 wrapper).

**Consequences:**
- (+) User can iterate on prompts / editorial voice without touching collection or rendering.
- (+) Cache hit on `rerender` + `dry-run` iterations keeps dev cost low.
- (−) First run each morning is a cold cache → no saving on day-over-day LLM spend beyond prompt caching's 5-min window.
- (−) Paywalled stories (BoF, WWD partial) will have thinner summaries; acceptance criterion AC6 and the `[요약본]` UI flag acknowledge this.
- (−) Windows-primary target means subprocess/path quirks (handled by always using `pathlib.Path` + forward-slash YAML paths).

**Follow-ups:**
- FU1: Measure first-week run times and LLM costs; tune `MAX_PER_CAT` and source list.
- FU2: If user wants Gmail Drafts, implement `delivery/gmail_draft.py` (OAuth installed-app flow, `users.drafts.create`).
- FU3: If clustering accuracy is a visible issue, swap `rapidfuzz` for a small `sentence-transformers` model (multilingual).
- FU4: Consider a Windows Task Scheduler `.xml` template for 7:30am auto-run in Phase 2.
- FU5: Expand `config/brands.txt` based on first-week error analysis.

---

## 9. Implementation Phases

### Phase 1 — MVP vertical slice (1–2 days)
**Goal:** user runs one command, gets a reviewable Korean `.eml` in `out/`, in < 10 minutes of wall-clock time.

- Steps 1–8 from §3.
- All AC1–AC13 passing.
- Windows 11 + Git Bash primary target; macOS/Linux work incidentally.

### Phase 2 — Polish (optional, post-MVP)
- `delivery/gmail_draft.py` — Google OAuth installed-app flow, creates a Gmail draft directly.
- `scheduler/` helpers — Windows Task Scheduler XML template + `setup-scheduler.ps1`; macOS `launchd` plist.
- Embedding-based clustering upgrade (swap inside `clusterer.py`).
- `insight_box` historical memory — feed last 3 days' insight boxes into the prompt for cross-day continuity.
- Feed health dashboard: simple CLI subcommand `python morning_brief.py health` reports per-feed success rate over last 14 days.

### Phase 3 — Out of scope for this plan (listed for Critic transparency)
- Per-client personalization (spec explicitly says 범용성 동일 메일).
- Web dashboard, subscription UI, auth system.
- Crawling Instagram/TikTok.
- 20+ recipient broadcast infra.
- Realtime alerts.

---

## Open Questions (for `.omc/plans/open-questions.md`)

- OQ1: Does the user want subject-line A/B variants or stick with `"[소비재 트렌드 조간] YYYY-MM-DD …"` as proposed? — affects `eml_builder.py` only.
- OQ2: Should `config/brands.txt` be seeded (we propose a starter list of ~50 consumer brands) or left empty for the user to curate? — affects clustering quality for Fashion/Beauty.
- OQ3: Preferred time zone for `generated_at` — KST fixed, or local-machine? — default to KST; trivial to flip.
- OQ4: If a category yields fewer than 2 clusters on a slow news day, should the section be dropped, use a single item, or display a placeholder "해당일 유의미한 이슈 없음"? — plan assumes placeholder; confirm.
- OQ5: Is the user comfortable with the Anthropic API key alone, or do they want a provider-abstraction env var ready from day one? — plan exposes `LLM_PROVIDER` but only implements Anthropic.
