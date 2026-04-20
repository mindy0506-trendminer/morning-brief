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
- **Anthropic API key** with access to `claude-haiku-4` and `claude-sonnet-4-6`

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
  db.py           SQLite schema (articles, clusters, entity_history, runs)
```

### Two-call LLM pipeline

```
scored CandidateCluster list
        |
        v
  [Call A — claude-haiku-4]
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
