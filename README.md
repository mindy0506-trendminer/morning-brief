# 소비재 트렌드 조간 브리핑 (Morning Brief)

소비재(패션·뷰티·식품·리빙·호스피탈리티) 분야 최신 뉴스를 매일 아침 자동으로 수집·요약해
정적 HTML 사이트(`out/index.html`)로 발행하는 CLI 파이프라인입니다.

A local Python CLI that collects RSS news from 15+ specialized feeds, pre-clusters duplicates,
scores novelty and diffusion in Python, calls Anthropic's Claude (Haiku → Sonnet two-call pipeline)
to write a Korean briefing, and publishes a ready-to-read static site at `out/index.html` —
all in under 2 minutes.

> **PR-4 change.** The legacy `.eml` output path was retired. The static site
> generator is now the sole renderer. The prior EML renderer + tests are
> archived at the git tag `pre-renderer-deletion` and can be recovered with
> `git checkout pre-renderer-deletion -- morning_brief/renderer.py tests/test_renderer.py`.

---

## Prerequisites

- **Python 3.11+** (tested on 3.12.10)
- **Windows / macOS / Linux** — Windows users should use **Git Bash** for the commands below
- **Git Bash on Windows**: `source .venv/Scripts/activate` (not PowerShell `Activate.ps1`)
- **Anthropic API key** with access to `claude-haiku-4-5` and `claude-sonnet-4-6`

---

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# source .venv/bin/activate      # macOS / Linux

# 2. Install the package and dev dependencies
pip install -e .[dev]

# 3. Configure environment variables
cp .env.example .env
# Edit .env and set:
#   ANTHROPIC_API_KEY=sk-ant-...
#   BRIEF_SENDER=Morning Brief <brief@yourcompany.com>
#   BRIEF_RECIPIENTS=you@yourcompany.com,teammate@yourcompany.com

# 4. Smoke test — no network calls, no API key required
python morning_brief.py dry-run

# 5. Full pipeline — requires a valid API key and internet access
python morning_brief.py run
```

---

## Usage

### Full pipeline

```bash
python morning_brief.py run [--limit-per-cat N]
```

Collects live RSS articles, runs the two-call LLM pipeline (Call A: Haiku clustering,
Call B: Sonnet Korean briefing), and publishes the static site at `out/index.html`
(archived snapshots under `out/YYYY/MM/DD/`).

`--limit-per-cat N` caps items per category to N (default: 3).

### Dry-run (fixture data, zero API calls)

```bash
python morning_brief.py dry-run
```

Uses `tests/fixtures/sample_articles.json` and `tests/fixtures/mock_call_*.json`
instead of real feeds and real API calls. Completes in under 30 seconds.
Ideal for CI and local iteration.

### Re-render from persisted artifacts

```bash
python morning_brief.py rerender <run_id>
```

Re-generates the static site from a previous run's persisted `call_b_response.json`
and `key_issues.json` without any API calls. `<run_id>` is the directory name
under `.omc/state/briefing/runs/` (format: `YYYY-MM-DD-HHMMSS`).

---

## Output

The pipeline writes the live static site to `out/index.html` and archives a
dated snapshot under `out/YYYY/MM/DD/`.

- **Open `out/index.html` in any browser** to read the briefing.
- All source links are clickable.
- Review the briefing, then share the URL / folder with the team.

---

## Configuration

All configuration files live in `config/`.

| File | Purpose |
|---|---|
| `config/sources.yml` | RSS feed list — name, URL, language, category hint, source type, status |
| `config/categories.yml` | Keyword lists per category used for auto-assignment when no category hint is given |
| `config/brands.txt` | Brand alias mapping (`자라=Zara`, `Nike`, etc.) — drives cross-language entity extraction |
| `config/editorial.md` | Editorial guidelines injected as the Call B system prompt suffix |

To add a new feed, append an entry to `sources.yml`:

```yaml
sources:
  - name: My New Feed
    url: https://example.com/rss
    language: en                    # en or ko
    source_type: SpecializedMedia   # TraditionalMedia | SpecializedMedia | CuratedTrendReport
    category_hint: Beauty           # optional — skips keyword matching if set
    status: confirmed               # confirmed | uncertain
```

---

## PII Note

The static site under `out/` does not embed recipient email addresses. The
legacy `REDACT_RECIPIENTS=1` guard applied only to the retired `.eml` output
path; it is now a no-op but remains honoured by env-loading helpers for
backward compatibility with older automation. `out/` is excluded from version
control via `.gitignore`.

---

## Architecture

The pipeline has six modules:

```
morning_brief/
  cli.py          CLI entry point — arg parsing, env loading, pipeline orchestration
  collector.py    RSS fetching, HTML enrichment, cross-language entity extraction (R6)
  selector.py     Pre-clustering (same-language near-dupes via rapidfuzz),
                  novelty/diffusion scoring, top-N picker
  summarizer.py   Two-call LLM pipeline + Blocker-3 section finalization
  site/           Static-site generator (Jinja2 templates + archive writer)
  db.py           SQLite schema (articles, clusters, entity_history, runs,
                  briefed_articles)
```

### Cross-run article dedup

An article's `canonical_url` must appear in **at most one** completed briefing
across the lifetime of the DB. After a successful run, every article that
reached the final briefing is recorded in the `briefed_articles` table
(keyed by `(article_id, run_id)`). On every subsequent run, the pipeline
pre-filters the candidate pool against this ledger so the same article
cannot resurface once it has been published — even if the underlying feed
keeps serving it for days.

Marking happens **after** renderer success, so Call B failures and render
errors leave articles eligible for the next run. Set
`MB_NO_DEDUP_PERSIST=1` to opt out of marking during repeated local
dry-runs.

### Two-call LLM pipeline

```
scored CandidateCluster list
        |
        v
  [Call A — claude-haiku-4-5]
  Input : pre-cluster titles + entity lists (~2 500 tokens)
  Output: merged clusters with cross-lingual flags + canonical Korean entity names
        |
        v
  R1 sanity checks (category-span ≤2, time-span ≤72h)
  Python rescore (novelty + diffusion recomputed on merged clusters)
  Blocker-3 filter (category renders iff ≥1 cluster at threshold)
        |
        v
  [Call B — claude-sonnet-4-6]
  Input : filtered KeyIssue list (~2 800 tokens)
  Output: LLMBriefing JSON — exec_summary_ko (3 lines), sections, insight_box_ko
          (no numeric scores — all 4 LLM models use ConfigDict(extra="forbid"))
        |
        v
  Site generator writes out/index.html + out/YYYY/MM/DD/ archive snapshot
```

Both calls use `cache_control: {"type": "ephemeral"}` on the system block for
prompt-cache hit savings on repeated runs within the 5-minute TTL window.

State is persisted under `.omc/state/briefing/`:

```
.omc/state/briefing/
  briefing.db            SQLite database (articles, entity_history, clusters, runs)
  runs/
    YYYY-MM-DD-HHMMSS/
      call_a_response.json
      call_b_response.json
      key_issues.json
```

---

## Testing

```bash
python -m pytest tests/ -v
```

Should report **82+ tests passing**. The dry-run pipeline test is the best
first integration check:

```bash
python -m pytest tests/test_end_to_end_dry_run.py -v
```

Test files and their coverage:

| File | AC coverage |
|---|---|
| `test_end_to_end_dry_run.py` | AC1 (dry-run <30s), AC2 (section structure), AC8 (cross-lingual merge), AC13 (rerender), AC15 (stage durations) |
| `test_collector.py` | AC12 (insufficient feeds), AC17 (R6 cross-language entity extraction) |
| `test_selector.py` | AC4 (1–3 items), AC9 (novelty warmup) |
| `test_summarizer.py` | AC3 (pydantic validated), AC10a/b (cache_control), AC14 (extra-forbid), AC16 (R1 sanity) |
| `test_site_*` | Site generator, templates, search index, archive, macro integration |
| `test_ac_coverage.py` | AC5 (primary source URL http), AC7 (duration <600s), AC11 (valid HTML document), AC12 (SystemExit guard), AC15 (per-stage caps) |
| `test_models_forbid.py` | AC3/AC14 (pydantic model strictness) |
| `test_legacy_removed.py` | PR-4 guard — renderer module + `--renderer` flag are gone |
| `test_db_bootstrap.py` | Schema bootstrap idempotency |

---

## Deployment (GitHub Actions + Pages)

The production pipeline is a single GitHub Actions workflow,
[`.github/workflows/daily-brief.yml`](.github/workflows/daily-brief.yml),
that runs daily at **07:00 KST** (`22:00 UTC` the previous day) and publishes
the resulting static site to GitHub Pages.

### One-time setup

1. **Enable Pages.** `Settings → Pages → Source: GitHub Actions`.
2. **Add secrets.** `Settings → Secrets and variables → Actions → New repository secret`:
   - `ANTHROPIC_API_KEY` — your Claude API key
   - `BRIEF_SENDER` — e.g. `Morning Brief <brief@yourcompany.com>`
   - `BRIEF_RECIPIENTS` — comma-separated list (legacy, retained for CLI contract)
3. **Optional tuning env vars** (defined inline in the workflow):
   - `MB_MAX_COST_USD` — daily budget cap (default `1.5`). Exceeding it exits
     with code `5` *before* any file write (plan v2 §D9).
   - `TZ=Asia/Seoul` — drives the KST date rendered on the page.

### Workflow anatomy

```
schedule: 0 22 * * *     ← daily at 07:00 KST
concurrency: daily-brief ← cancel-in-progress: false (never kill in-flight)
Retry ladder: 3 attempts × 10-min backoff (OQ11)
  └─ Attempt 3 forces MB_FORCE_PARTIAL_BANNER=1 so the banner
     surfaces on the previous day's site during failures.
Pagefind: npx pagefind --site out  ← production search index (§D5)
Commit archive: out/archive/** + out/search_index.json → main
Deploy: actions/deploy-pages@v4
```

### Expected URL

`https://<owner>.github.io/<repo>/` — visible after the first green run.

### Manual trigger

`Actions → Daily Morning Brief → Run workflow`. Useful for smoke-testing the
retry ladder or re-publishing after a manual fix to `out/archive/`.

### Monitoring

- **Actions tab** — each run is green / red. Red means all 3 attempts
  failed; the last successful site remains deployed and a partial-build
  banner is shown on the page.
- **Commit log on `main`** — every successful run produces a
  `chore(archive): daily brief YYYY-MM-DD` commit as persistence (Git-as-DB
  per plan v2 §D4).

### Troubleshooting deployment

- **3 consecutive failures** → last successful site stays visible, the
  partial-build banner is shown ("전일 브리핑 표시 중 — 자동 재시도 실패"),
  manual intervention required. Check Actions logs, fix root cause, re-run
  via `workflow_dispatch`.
- **Exit code 5 (cost cap)** → raise `MB_MAX_COST_USD` in the workflow `env:`
  block or trim the candidate pool (`--limit-per-cat`).
- **Exit code 6 (partial build)** → the banner is rendered automatically.
  Check `out/archive/YYYY/MM/DD.html` on the next successful run.
- **Rebuild a specific day** → delete `out/archive/YYYY/MM/DD.{html,json}`
  (and any `-revN.html` siblings) on `main`, then re-run the workflow.
- **Pagefind missing locally** → `python morning_brief.py dry-run` still
  works without `npx pagefind`; the Pagefind UI silently falls back to the
  JSON-based `search.js` form, and the sidebar remains functional.

---

## Troubleshooting

**"Python not found"**
: Try `python3` instead of `python`, or verify Python 3.11+ is on your PATH:
  `python --version`

**"ANTHROPIC_API_KEY missing"**
: Ensure `.env` exists in the repo root and contains `ANTHROPIC_API_KEY=sk-ant-...`.
  Run `cp .env.example .env` if it doesn't exist, then edit it.

**"Cache not hitting" (낮은 캐시 적중률)**
: Prompt-cache hits only occur within a 5-minute TTL window on the same system prompt.
  Day-over-day cache hits are not guaranteed and are not tested — this is expected behavior.

**"Insufficient feeds: only X feeds returned articles (threshold 3)"**
: At least 3 distinct RSS feeds must successfully return ≥1 article after parsing.
  Check `config/sources.yml` for misconfigured URLs, and verify network access.
  Run `python morning_brief.py dry-run` (which uses fixture data) to confirm the
  rest of the pipeline is working correctly.

**"call_a schema error" / SystemExit(3)**
: Call A (Haiku) returned a malformed JSON response twice in a row.
  This is typically a transient API issue; retry after a few minutes.

**Windows path issues with Git Bash**
: Always use forward slashes in paths. If `python` is not found in Git Bash,
  add your Python installation directory to the Windows PATH environment variable.
