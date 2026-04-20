# Morning Brief Web — Implementation Plan v2

**Source spec:** `.omc/specs/deep-interview-morning-brief-web.md` (di-2026-04-19-morning-brief-web, 7.9% ambiguity, 100% ontology convergence)
**Mode:** Ralplan consensus — **SHORT** (brownfield extension; not `--deliberate`)
**Author:** Planner (iteration 2/5; Architect REVISE + Critic ITERATE resolved)
**Date:** 2026-04-19
**Supersedes:** `.omc/plans/morning-brief-web-plan-v1.md`

---

## 0. CHANGELOG (v1 → v2)

All changes directly address Architect REVISE and Critic ITERATE blocking items.

| # | Blocking issue | v1 claim | v2 fix |
|---|----------------|---------|--------|
| **1** | Test count audit | "82 tests"; renderer=25, summarizer=42, models_forbid=3, db_bootstrap=1, ac_coverage=7, end_to_end=2, collector=7, selector=13 | **83 tests verified via `pytest --collect-only -q`**: collector=16, selector=13, summarizer=13, renderer=9, ac_coverage=6, end_to_end=5, models_forbid=15, db_bootstrap=6. Phase F matrix rebuilt row-by-row (§D8). Driver 2 updated. |
| **2** | 5-lang Literal widening | Claimed "reuse" | Split A5 into A5a–A5d; acknowledged as **principled exception** ("reuse where possible, refactor where necessary"); Principle 1 renamed. |
| **3** | Partial-build atomicity | `SystemExit(5)` mid-pipeline, no atomic writes | D9 rewritten: **pre-flight cost estimate before any write**, atomic `.tmp` + `os.replace()`, GH Actions `concurrency: group=daily-brief, cancel-in-progress: false`, exit-code map (1/2 existing, 3/4 summarizer, **5=cost-cap pre-flight**, **6=partial-build banner path**), partial-build banner template. |
| **4** | Atomic 28-test swap | "1 big PR" | D8 replaced with **5-PR staged sequence** (data → new-renderer-flagged → flip-default → delete-old → CI). |
| **5** | D2 SCTEEP in Haiku unblessed | Round 6 only blessed renderer replacement | Added **D2-D: dedicated Sonnet `macro_tagger.py` pass** with cost delta +$0.03–0.08/day. **Pick: D2-D** (explicit rationale; Round 6 did not bless Haiku for SCTEEP). |
| **6** | D10 9-way union | Permanent maintenance debt | **D10-A picked**: full canonical rename + one-shot `scripts/migrate_categories.py` rewriting DB + fixtures; legacy_map deleted. (D10-B kept as contingency.) |
| **7** | $0.42/day ungrounded | Priced from first principles | **Phase A0 (pre-planning measurement)** added: 3 dry-runs, extract token counts from `briefing.db` + logs, cite observed range; cap sized to 2.5× upper bound. |
| **8** | Phase F AC 10/15/18/19/20/21/22 gaps | Not covered | 7 new tests added to Phase F (F10–F16 below). |

**Non-blocking improvements applied:**
- Playwright kept (weight justified by PDF AC); fallback manual-QA checklist documented in F6 if install exceeds 2 min on Actions.
- `concurrency` block documented in E1.
- ADR "Alternatives considered" expanded with build-time numbers for Node/11ty.
- Risk #2, #5, #7 rewritten in owner/trigger/action format.
- Phase F bumped **M → L** (8 deleted + 16 new = 24 test churn).

---

## 1. RALPLAN-DR Summary

### 1.1 Principles (5)

1. **Reuse where possible, refactor where necessary.** Collector/selector/summarizer cores are preserved; `renderer.py` is replaced; `Article.language` / `CandidateCluster.language` Literals **are deliberately widened** from `["ko","en"]` to `["ko","en","ja","zh","es"]` — a principled exception because source-language expansion is the spec's hard requirement and cannot be aliased.
2. **Git-as-DB.** Daily HTML+JSON accumulated via commits; no external DB/storage; 0원 hosting preserved.
3. **Static-first, client-rich.** Search/navigation/PDF all run in the browser on static assets. Any server-side dependency breaks the GH Pages free-tier contract.
4. **Config-driven editorial.** 6-tab structure, company tags, selection prompts all declared in `config/*`; operators adjust without code deploys.
5. **Additive schema, versioned + migrated.** `LLMBriefing.schema_version` bumped `v2 → v3`. Legacy category names are **migrated once** via `scripts/migrate_categories.py` (not permanently aliased) so Pydantic Literals stay tight.

### 1.2 Decision Drivers (top 3)

1. **Zero-cost daily reproducibility.** GH Actions cron + Pages + Git is free and reproducible. Any option violating this is rejected immediately.
2. **Preserve the 83-test safety net.** Concretely: of 83 tests, **55 are preserved as-is, 9 are deleted (test_renderer.py), 5 need fixture updates (test_end_to_end_dry_run.py + language widening), 14 stay but may gain cases (test_models_forbid.py), and 16 are added new** (see §D8 matrix).
3. **Daily build ≤10 min end-to-end with bounded API cost.** Cost bound is **measured** (Phase A0), not assumed. Cap sized at 2.5× observed p95.

### 1.3 10 Key Decision Points

---

#### D1. Static HTML generator architecture

**Options:**
- **(A) Jinja2 + Python `site_generator.py`** — already a dep; summarizer imports Jinja2 (`morning_brief/summarizer.py:22`). Team owns Python. **Build time: ~2s local.**
- (B) 11ty (Node.js) — richer static ecosystem, but adds Node install (~40s cold cache on Actions) + `npm install` (~25s) + `npx @11ty/eleventy` (~8s); total **~73s added to build**.
- (C) Pure Python f-strings — minimal deps; unmanageable for 6 tabs × 2 page types × partials.

**Pick: (A) Jinja2.** Deps already present, no Node bootstrap cost, 11ty's added 73s against a 10-min budget is dead weight for our scope.

(Template structure unchanged from v1 §D1.)

---

#### D2. MacroTab pipeline — separate or shared?

**Options:**
- (A) Fully separate `macro_pipeline.py` — duplicate feeds + duplicate selector. Rejected: doubles API cost.
- (B) Shared collection + SCTEEP tagging **in Call A (Haiku)** — v1's choice.
- (C) Shared collection + no SCTEEP dimensions, just a "Macro" category flag. Rejected: violates AC ("SCTEEP 6차원 태그를 카드별 시각화").
- **(D) Shared collection + dedicated Sonnet `macro_tagger.py` pass** — after Call A clusters, a new Sonnet call with macro-specific few-shots labels MacroTab candidates with 1–3 SCTEEP dims. Tagging runs ONLY on the ~50 candidates routed to MacroTab (not all 300), bounding cost.

**Pick: (D).** Rationale:
- Round 6 (`deep-interview-morning-brief-web.md:242`) blessed **renderer replacement only** — it did NOT bless expanding Haiku's responsibility. Putting SCTEEP inside Call A silently widens Haiku's prompt, degrading clustering accuracy (known failure mode when Haiku juggles two classification heads).
- Dedicated Sonnet pass on ~50 candidates: input ~15k tokens, output ~2k tokens → **+$0.03–0.08/day** over v1's $0.42 estimate. Upper bound fits the cap comfortably.
- Isolation: if SCTEEP quality is poor, tune `macro_tagger.py` few-shots without touching Call A regression surface.

**Contract:** `macro_tagger.tag_macro_candidates(candidates: list[Cluster]) -> list[MacroCluster]` where `MacroCluster` extends `Cluster` with `sceep_dimensions: list[Literal["S","C","T","E1","E2","P"]]` (1–3 items, non-empty).

---

#### D3. `companies.yml` schema — **unchanged from v1.** Pick: (B) YAML.

---

#### D4. Archive URL structure — **unchanged from v1.** Pick: (A) `archive/YYYY/MM/DD.html`, append-only.

See D9 for the **atomic write contract** that makes "append-only" enforceable.

---

#### D5. Search engine — **unchanged from v1.** Pick: (A) Pagefind.

---

#### D6. PDF export — **unchanged from v1.** Pick: (A) browser `window.print()` + `print.css`.

Playwright dep risk: if `playwright install chromium` exceeds 2 min on Actions cold cache, Phase F falls back to F6b (manual QA checklist committed to `docs/qa/pdf_export.md`).

---

#### D7. GitHub Actions structure — see D9 for the **concurrency** addition.

---

#### D8. Test compatibility — **REBUILT FROM VERIFIED COUNTS**

**Source of truth:** `pytest --collect-only -q` on 2026-04-19 → **83 tests**.

| File | **Actual count** | Fate in v2 | Detail |
|------|---:|------------|--------|
| `test_collector.py` | **16** | **Keep 16; add 3** | companies.yml path is additive; 5-lang fixtures updated (A5c) but language assertion tests unaffected — `Article.language` union widens, never narrows. 3 new tests for JA/ZH/ES entity extraction. |
| `test_selector.py` | **13** | **Keep 13; add 2** | `company_tag_score` added via `use_company_tag=True` opt-in (backward compat). 2 new tests: company_tag weighting and 40/30/30 composition. |
| `test_summarizer.py` | **13** | **Keep 13; add 3** | Category Literal migrates v2→v3 in `CallAClusterOut.category_confirmed` AND `LLMBriefing.sections`. One-shot `scripts/migrate_categories.py` rewrites existing fixtures + DB rows (D10-A). No runtime legacy_map. 3 new tests: schema_version=v3 roundtrip, Sonnet macro_tagger contract, migration script idempotence. |
| `test_renderer.py` | **9** | **Delete all 9** (PR-4) | All 9 assertions are eml/subject/email-module specific (verified: `test_eml_structure`, `test_build_subject_*`, `test_render_*`, `test_score_pills_come_from_python_not_llm`, `test_eml_redact_recipients`, `test_html_no_external_stylesheet`). Superseded by `test_site_generator.py`. |
| `test_ac_coverage.py` | **6** | **Keep 5; rewrite 1; add 7** | Rewrite: AC11 (eml parseable) → AC_PDF_EXPORT. Keep: source link dedup, run≤10min, feed≥3, stage caps, entity matching. Add 7: AC10, 15, 18, 19, 20, 21, 22 (see F10–F16). |
| `test_end_to_end_dry_run.py` | **5** | **Keep signatures; update fixture assertions** | Assert `site/index.html` + `archive/2026/04/18.html` + `data/archive_index.json` instead of `.eml`. 5 tests preserved; bodies updated. |
| `test_models_forbid.py` | **15** | **Keep 15; add 1** | `extra="forbid"` still enforced on all strict models. Add 1 test: 5-language `Article.language` acceptance (and rejection of old invalid values, e.g. `"fr"`). |
| `test_db_bootstrap.py` | **6** | **Keep 6** | `articles.company_tags` column additive; bootstrap migration is idempotent (tested implicitly by existing schema test). |
| **Total** | **83** | **Preserved: 73 tests** (55 untouched + 18 whose bodies evolve but signatures persist). **Deleted: 9 tests** (renderer). **New: 16 tests** (F2–F16 site/macro/two-stage/companies/search/AC 10,15,18,19,20,21,22). **Net final: 90 tests.** | — |

**Staged PR sequence (replaces v1's "atomic 28-test swap"):**

| PR | Scope | Tests green at end of PR | Risk |
|---|-------|-------------------------|------|
| **PR-1** | Data layer: `config/companies.yml`, widen `Article.language`/`CandidateCluster.language` Literals to 5 langs, add `CompanyTag` model + `articles.company_tags` column. Run `scripts/migrate_categories.py` once against fixtures (categories v2→v3). | 83 existing + model_forbid new → **84** | Contained to schema; no behavior change yet. |
| **PR-2** | Add `morning_brief/site/` tree + `site_generator.py` + templates + static assets. CLI gains `--renderer=site` flag (default stays `eml`). New tests added but `test_renderer.py` untouched. | 84 + site/companies/macro/two-stage tests → **~95** (both renderers green in parallel) | New code behind flag; fully reversible. |
| **PR-3** | Flip CLI default `--renderer=site`; `--renderer=eml` remains as opt-in fallback for 1 week. `test_end_to_end_dry_run.py` updated to assert site outputs. | 95 | CLI default change; reversible. |
| **PR-4** | Delete `morning_brief/renderer.py` + `tests/test_renderer.py` (9 tests); remove `--renderer=eml` flag. | 95 − 9 = **86** | One-way; previous PRs prove site-path stable. |
| **PR-5** | `.github/workflows/daily-brief.yml` + Pages config + `concurrency` block + `ANTHROPIC_API_KEY` secret. Add AC tests F10–F16. | 86 + 7 AC = **93**. Sitting above spec's "~83 preserved" floor. | Observable in dry-run before merge. |

**Rollback contract:** any PR can be reverted independently because each leaves the full test suite green.

---

#### D9. Daily cost cap + partial-build semantics — **REBUILT**

**Cost estimate (v1 preserved, now cross-checked by A0):**
- Call A (Haiku): ~$0.014/day
- Call B (Sonnet): ~$0.405/day
- **D2-D macro_tagger (Sonnet, 50 candidates)**: ~$0.05/day (range $0.03–0.08)
- **Total model cost: ~$0.47/day** (up from v1's $0.42 after D2-D correction)

**Cap mechanism — pre-flight, no mid-pipeline abort:**
```
Phase order inside run_pipeline():
  1. collect()  → articles (no model calls)
  2. precluster() + score() → candidates (no model calls)
  3. estimate_cost(candidates, editorial_prompt) → $X  [uses tiktoken/anthropic token count]
  4. IF $X > --max-cost-usd:  raise SystemExit(5)   ← BEFORE any write
  5. call_a_haiku() → clusters (no file writes yet)
  6. macro_tag_sonnet() → macro_clusters
  7. call_b_sonnet() → briefing (no file writes yet)
  8. site_generator.build_site(briefing) → writes to site/.tmp/ and archive/.tmp/
  9. os.replace() from .tmp → final paths   ← ATOMIC
 10. git commit && push
```

**Atomic write contract:**
- `site_generator.build_site(out_dir)` writes every file as `out_dir/<path>.tmp` first.
- After all files written, a single `_commit_outputs()` helper calls `os.replace(tmp, final)` per file in a deterministic order (deepest paths first) so partial filesystem state is never observable.
- `archive/YYYY/MM/DD.html` existence check: if present AND content-hash differs from new content, refuse to overwrite; write `archive/YYYY/MM/DD-revN.html` instead and log WARN. **AC 10 (permanent URL) enforced here.**

**Exit code map (adds 5 and 6; existing unchanged):**
| Code | Meaning | Raised in |
|---:|---------|-----------|
| 1 | General (config/IO/unexpected) | `cli.py:56, 264, 270, 277, 280` (existing) |
| 2 | Dry-run fixture load failure | `cli.py:115` (existing) |
| 3 | Call A (Haiku) failure | `summarizer.py:392` (existing) |
| 4 | Call B (Sonnet) failure | `summarizer.py:511` (existing) |
| **5** | **Pre-flight cost cap exceeded** | `cli._run_pipeline` before any write (**new**) |
| **6** | **Partial build — some tabs failed but best-effort HTML generated** | `site_generator.build_site` (**new**, writes "부분 브리핑" banner in `partial_banner.html` partial) |

**GH Actions concurrency (new):**
```yaml
concurrency:
  group: daily-brief
  cancel-in-progress: false   # do not interrupt a build mid-commit; queue the next
```
Prevents double-builds if a manual re-run overlaps the 07:00 KST cron.

**Partial-build banner:** if exit code 6, `site_generator` still renders `index.html` with a red banner ("오늘 브리핑은 일부 탭 장애로 불완전합니다") and the failing tab shows a retry hint. Banner template: `morning_brief/site/templates/partials/partial_banner.html`.

---

#### D10. `categories.yml` migration — **D10-A picked (full rename + one-shot migration)**

**Options recap:**
- **(A) Full canonical rename + one-shot `scripts/migrate_categories.py`.** `categories.yml` contains ONLY {`MacroTrends`, `F&B`, `Beauty`, `Fashion`, `Lifestyle`, `ConsumerTrends`}. Migration script rewrites `briefing.db` rows and any fixtures in-place. Literals stay tight (6-way). No `legacy_map` at runtime.
- (B) 9-way union + CI guard + 3-month deprecation — contingency only.

**Pick: (A).** Rationale:
- Critic's objection to v1: 9-way Literal union is maintenance debt forever. Fixtures would continue producing legacy names indefinitely.
- One-shot migration is **bounded work** (one script, one run, deleted after merge).
- Script: reads `briefing.db`, UPDATE `clusters` + `articles` rows WHERE `category IN ('Food','Living','Hospitality')` → {Food→F&B, Living→Lifestyle, Hospitality→Lifestyle}. Idempotent (checks target value before write).
- Fixtures under `tests/fixtures/` rewritten via `jq`/`python` one-pass; commit includes the script AND the rewritten fixtures in PR-1 so review surface is a single diff.

**Fallback (D10-B):** if the team discovers a hidden consumer (e.g., external tool reading `briefing.db`), activate the 9-way union + `scripts/check_no_legacy_category.py` pre-commit hook with 3-month deprecation. Defined but NOT installed by default.

---

## 2. Detailed Implementation Plan — File by File

### Phase A0: Cost measurement (prerequisite, S)

| # | Task | Output | Size |
|---|------|--------|------|
| A0-1 | Run `morning-brief run --dry-run` 3× with existing `tests/fixtures/dryrun/` | 3 log files + 3 `briefing.db` snapshots | S |
| A0-2 | Extract `prompt_tokens` + `completion_tokens` per call from `briefing.db.run_stats` (or stderr if absent) | `.omc/research/cost_baseline.md` table | S |
| A0-3 | Back-compute $/run using public Anthropic pricing (Haiku $0.25/$1.25 per MTok, Sonnet $3/$15 per MTok, +20% contingency for 5-lang token inflation) | Observed range + p95, cap = 2.5× p95 | S |
| A0-4 | Cite in D9 | Updated table | S |

**Expected deliverable:** a citable range like "$0.31–$0.58 observed in 3 runs; cap set at $1.50 = 2.5× upper bound". If observed range exceeds $0.80, escalate to user before Phase B.

### Phase A: Foundation (S–M)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| A1 | `config/companies.yml` (new) | D3 schema. Seed with brands.txt 44 companies + 56 additions. | — | M |
| A2 | `config/categories.yml` (modify) | D10-A canonical 6 categories only. Delete `legacy_map` entry. | A1 | S |
| A3 | `config/sources.yml` (modify) | Add JA/ZH/ES feeds, ≥3 per language, ≥15 total. Document language field = 5 distinct values. | — | S |
| A4 | `config/editorial.md` (modify) | Add SCTEEP labeling guidance + Top30→Top15 selection prompt section. | — | S |
| **A5a** | `morning_brief/models.py` | **Widen `Article.language` Literal to `["ko","en","ja","zh","es"]`.** Single-line change at `models.py:23`. | — | XS |
| **A5b** | `morning_brief/models.py` | **Widen `CandidateCluster.language` to same 5-lang Literal.** Line 39. | A5a | XS |
| **A5c** | `tests/fixtures/*.json` (all) | Grep every fixture with `"language":` and confirm each value is in the new set. None should fail but **prove it** via `scripts/validate_fixtures.py` one-shot. | A5a, A5b | S |
| **A5d** | `morning_brief/summarizer.py` (_dedupe hash) | Audit `_hash_for_dedup()` / cross-lingual merge logic: verify no code assumes `language in ("ko","en")`. Add test `test_cross_lingual_dedupe_5lang`. | A5a | S |
| A5e | `morning_brief/models.py` | Add `CompanyTag` enum (`대기업`/`유통`/`혁신스타트업`), `Article.company_tags: list[CompanyTag]`, `NewsCard`, `MacroCluster.sceep_dimensions`, `LLMBriefing.schema_version: Literal["v3"]`, 6-category Literal for `CallAClusterOut.category_confirmed` + `LLMBriefing.sections` keys. | A5a–A5d, A2 | M |
| A6 | `morning_brief/db.py` | Add `articles.company_tags` JSON column bootstrap migration; idempotent. | A5e | S |
| **A7** | `scripts/migrate_categories.py` (new, one-shot) | Read `briefing.db`, rewrite `clusters.category` + `articles.category` from legacy → canonical. Dry-run flag. Logs every change. Deleted after PR-1 merges. | A2 | S |

### Phase B: Pipeline extensions (M)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| B1 | `morning_brief/collector.py` | `load_companies()` + `ingest_entities` fills `article.company_tags`. Extend entity-extract regex to JA/ZH/ES. | A1, A5e | M |
| B2 | `morning_brief/selector.py` | `score_candidates(use_company_tag=False)` default preserves old tests; `use_company_tag=True` path uses 40/30/30. | A5e, B1 | M |
| B3 | `morning_brief/two_stage_selector.py` (new) | stage1=auto score Top30/tab; stage2=Sonnet judge via `editorial.md` → Top15. | B2, A4 | M |
| **B4** | `morning_brief/macro_tagger.py` (new) | **D2-D dedicated Sonnet pass.** Input: up to 50 MacroTab candidates. Output: `list[MacroCluster]` with `sceep_dimensions: list[Literal["S","C","T","E1","E2","P"]]` (1–3 items). Uses prompt cache (persistent system prompt). | A5e | M |
| B5 | `morning_brief/summarizer.py` | `_CATEGORIES` → 6 canonical names. Integrate TwoStageSelector + macro_tagger. Call A prompt no longer asks for SCTEEP (D2-D separates it). | A4, A5e, B3, B4 | M |

### Phase C: Static site generator (L)

Unchanged from v1 C1–C11, plus:

| # | Files | Addition |
|---|-------|----------|
| C12 | `morning_brief/site/templates/partials/partial_banner.html` (new) | Red banner for exit-code-6 partial builds (D9). |
| C13 | `morning_brief/site/site_generator.py` | Implement `.tmp → os.replace()` atomic writes (D9); implement permanent-URL collision check + `DD-revN.html` fallback. |

### Phase D: Aggregation & archive — **unchanged from v1** (D1–D5).

### Phase E: CI/CD (M)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| E1 | `.github/workflows/daily-brief.yml` (new) | cron `0 22 * * *` UTC = 07:00 KST next day. **`concurrency: group=daily-brief, cancel-in-progress: false`.** Steps: checkout → setup Python 3.11 → `pip install -e .[dev]` → install pagefind CLI → `TZ=Asia/Seoul morning-brief run --max-cost-usd=1.5` → `pagefind --site site/` → `git add site/ archive/ && git commit -m "auto-brief $(TZ=Asia/Seoul date +%Y-%m-%d)" && git push` → `actions/deploy-pages@v4`. Commit message uses KST date explicitly. | C11, D3 | M |
| E2 | `.github/workflows/pages-deploy.yml` (new) | Trigger on `push: paths: [site/**, archive/**]`. | E1 | S |
| E3 | Repo settings | `ANTHROPIC_API_KEY` secret; Pages source config. | E1 | S |
| E4 | `morning_brief/cli.py` (modify) | `--max-cost-usd` flag (default 1.5 after A0). Pre-flight estimate → SystemExit(5) before writes. Cost log appended to `archive/YYYY/MM/DD.json`. | Phase B | S |

### Phase F: Test harness (**L**, upgraded from M)

| # | Files | Change | Size |
|---|-------|--------|------|
| F1 | `tests/test_renderer.py` (delete) | Delete in PR-4, all 9 tests. | — |
| F2 | `tests/test_site_generator.py` (new) | 6-tab structure, 15 cards/tab, country indicator, link validity, SCTEEP pill, CompanyTag pill, 375px viewport assertion (BeautifulSoup). | L |
| F3 | `tests/test_macro_tagger.py` (new) | D2-D contract: ≥1 dim, ≤3 dims, dims ⊂ {S,C,T,E1,E2,P}, no MacroTab duplication. | M |
| F4 | `tests/test_two_stage_selector.py` (new) | Top30→Top15, 40/30/30 weighting, editorial.md prompt loaded from file path (not hardcoded). | M |
| F5 | `tests/test_companies_tagging.py` (new) | YAML load + alias + tag + brands.txt coexistence. | M |
| F6 | `tests/test_pdf_export.py` (new) | Playwright headless → `page.pdf()` → parse pages count + metadata. Fallback `docs/qa/pdf_export.md` checklist if Playwright install >2min. | M |
| F7 | `tests/test_end_to_end_dry_run.py` (modify) | Assert site outputs in place of eml outputs. | M |
| F8 | `tests/fixtures/` (new) | `macro_cluster_sample.json`, `companies_tagging_sample.json`, `multilang_articles_ja_zh_es.json`. | M |
| F9 | `tests/test_search_indexer.py` (new) | Mock Pagefind CLI; verify output directory structure. | S |
| **F10** | `tests/test_ac_permanent_url.py` (new, AC 10) | Write `archive/2026/04/18.html` twice with different content → assert 2nd write creates `DD-rev1.html`, original untouched. Exercises `.tmp` + `os.replace` + collision detection. | S |
| **F11** | `tests/test_ac_editorial_from_file.py` (new, AC 15) | Monkey-patch `config/editorial.md` content → run TwoStageSelector stage2 → assert the new content appears verbatim in the Sonnet prompt. Guarantees no hardcoded prompt. | S |
| **F12** | `tests/test_ac_cron_kst.py` (new, AC 18) | Parse `.github/workflows/daily-brief.yml` → assert cron=`0 22 * * *`. Use `zoneinfo.ZoneInfo("Asia/Seoul")` to prove UTC 22:00 → KST 07:00 (with date rollover; commit message date = KST). | S |
| **F13** | `tests/test_ac_archive_commit.py` (new, AC 19) | Integration test using `tempfile.TemporaryDirectory` as a bare git repo. Run `build_site()` then simulate commit; assert HEAD tree contains `site/index.html` + `archive/YYYY/MM/DD.html` + `archive/YYYY/MM/DD.json`. | M |
| **F14** | `tests/test_ac_build_time.py` (new, AC 20) | Benchmark end-to-end build against fixture corpus with `@pytest.mark.timeout(600)` (10 min). Marked `slow`; runs in CI only. | S |
| **F15** | `tests/test_ac_sources_5lang.py` (new, AC 21) | Static parse `config/sources.yml` → assert `len(set(feed.language for feed in feeds)) == 5` and set equals `{ko,en,ja,zh,es}`. | S |
| **F16** | `tests/test_ac_feeds_per_lang.py` (new, AC 22) | Static parse `config/sources.yml` → assert each of 5 languages has ≥3 feeds AND total ≥15. | S |

**Phase F sizing:** L (delete 9 + add 16 = 25 test files of churn + test harness for SCTEEP + fixtures).

---

## 3. Acceptance Criteria Mapping

| Spec AC | Implemented by | Test |
|---------|----------------|------|
| 6 tabs, 거시매크로 first | C4, C6 tab_nav.html, C11 | F2 |
| 15 cards/tab | B3 TwoStageSelector | F2, F4 |
| SCTEEP 6-dim on MacroTab cards | **B4 macro_tagger.py (D2-D)**, C6 macro_card.html | F3 |
| Card = 1-line head + 3-line summary + source + link | C6 card.html, A5e NewsCard | F2 |
| Country indicator | C10 flags.py, C6 | F2 |
| Original headline in source section | A5e OriginalHeadline, C6 | F2 |
| Left date sidebar | C6 sidebar_dates.html, D2 | F2 |
| Year>Month>Day dropdown | D1 archive_indexer, D2 | F2 |
| Search bar top-left, full archive | D3 Pagefind, D4 | F9 |
| **AC 10: past-date permanent URL** | **D5, C13 atomic .tmp + collision→revN** | **F10** |
| Mobile 375px+ | C7 mobile-first | F2 |
| PDF export | C8 print.css, C9 pdf.js | F6 |
| Stage-1 40/30/30 Top30 | B2, B3 | F4 |
| Stage-2 Sonnet Top15 | B3 | F4 |
| **AC 15: editorial.md prompt from file** | **A4, B3** | **F11** |
| companies.yml 3-class tagging | A1, B1 | F5 |
| collector company recognition | B1 | F5 |
| **AC 18: 07:00 KST cron** | **E1** | **F12** |
| **AC 19: HTML+JSON committed to Git** | **E1** | **F13** |
| **AC 20: ≤10 min build** | **E1, A0 cost = time proxy** | **F14** |
| **AC 21: 5 languages in sources.yml** | **A3** | **F15** |
| **AC 22: ≥3 feeds/lang, ≥15 total** | **A3** | **F16** |
| Cross-lingual entity matching | A5d, B1 | existing test_collector + A5d new test |
| 83 existing tests honored per D8 matrix | D8 staged PRs | D8 per-PR counts |
| New HTML renderer tests | F2 | — |
| PDF export test | F6 | — |

All 22+ ACs mapped; each has a concrete Phase-F test.

---

## 4. Risk Callouts (owner / trigger / action format for #2, #5, #7)

1. **Jinja2 template sprawl.** Owner: Planner. Trigger: >15 templates OR duplicate card HTML detected. Action: extract shared fragment into `partials/_card_body.html`; add duplicate-render lint to F2.
2. **Git repo size growth.** Owner: Ops (you). Trigger: `du -sh site/` > 500 MB OR GitHub push returns size warning. Action: move >2-year-old `archive/YYYY/MM/*.json` into Git LFS (follow-up F/U-5 pre-written); `archive/*.html` stays in main tree.
3. **API cost spike on 5-lang.** Owner: Planner. Trigger: A0 baseline or any daily run >$0.80. Action: truncate Call B enriched_text to 300 chars, re-measure; if still >$0.80, reduce Top30 to Top20.
4. **Timezone handling.** Owner: CI. Trigger: F12 asserts drift. Action: pin `TZ=Asia/Seoul` explicitly in both the job env and commit message; KST has no DST so no seasonal drift.
5. **Renderer replacement breaking eml-based tests.** Owner: Planner. Trigger: PR-4 diff exceeds test-count delta predicted in D8. Action: pause PR-4; regenerate D8 matrix from HEAD; reconcile before deleting `renderer.py`.
6. **Pagefind CJK tokenization.** Owner: Ops. Trigger: user reports Korean substring miss post-launch. Action: add custom stopwords file; in-repo eval harness — out of scope for this plan.
7. **5-lang Literal widening breaks a hidden consumer.** Owner: Planner. Trigger: PR-1 CI red on `test_models_forbid` or downstream. Action: restore 2-lang Literal temporarily, add failing consumer to A5d audit list, widen again via intermediate `Literal["ko","en","ja"]` then `+zh,es` in two PRs.
8. **Playwright install exceeds 2 min on Actions.** Owner: CI. Trigger: F6 install step >120s. Action: switch F6 → F6b manual checklist `docs/qa/pdf_export.md`; remove Playwright from `[dev]` extras.

---

## 5. Non-Goals Reminder

(unchanged from v1 §5)

---

## 6. ADR (Architectural Decision Record)

**Decision:** Preserve the `morning_brief` Python CLI pipeline; replace `renderer.py` with a Jinja2-based static-site generator (`morning_brief/site/site_generator.py`); add a dedicated Sonnet `macro_tagger.py` pass for SCTEEP labeling; deploy via GitHub Pages + Actions; migrate legacy categories once via `scripts/migrate_categories.py` (no runtime legacy_map).

**Decision Drivers:**
1. 0원 hosting + reproducible daily build ≤10 min.
2. Preserve the 83-test safety net (73 retained, 9 deleted, 16 added → net 90).
3. API cost **measured in Phase A0** before caps are set; target median <$0.60/day.

**Alternatives considered (with concrete numbers):**
- **Full rewrite in Node/11ty/Astro.** Rejected. 11ty cold-cache build adds ~73s (40s Node install + 25s `npm ci` + 8s render) vs. Jinja2's ~2s; throws away 73/83 Python tests.
- **MacroTab as separate pipeline (D2-A).** Rejected: duplicates collection, ~2× API cost.
- **SCTEEP tagging inside Call A Haiku (D2-B, v1's pick).** Rejected: Round 6 did not bless widening Haiku's responsibility; classification-head interference is a known Haiku failure mode.
- **Lunr.js.** Rejected: CJK plugin fragmentation; Pagefind covers 5 langs natively.
- **weasyprint PDF.** Rejected: Git repo PDF accumulation violates 0원 storage target.
- **9-way category Literal union (v1's D10).** Rejected: permanent maintenance debt; replaced with one-shot migration script (D10-A). 9-way union retained as D10-B contingency.
- **Atomic single-PR replacement.** Rejected: Critic correctly flagged un-bisectable risk; replaced with 5-PR sequence where each PR keeps the suite green.

**Why chosen:** Meets zero-cost + reproducibility + editorial-flexibility while reusing ~88% of existing pipeline code. SCTEEP isolation in a dedicated pass is defensible and bounded (+$0.03–0.08/day). Staged PRs make rollback trivial.

**Consequences:**
- (+) Each of 5 PRs independently revertible; no "big bang" risk window.
- (+) Categories stay as 6-way Literal forever; no legacy debt.
- (+) SCTEEP quality can be tuned in `macro_tagger.py` few-shots without touching Call A.
- (−) `Article.language` / `CandidateCluster.language` widening is a breaking Pydantic contract change (mitigated by A5c fixture validation script).
- (−) Daily API cost ~$0.03–0.08 higher than v1 due to D2-D; still well under $1.50 cap.
- (−) Git repo grows ~55 MB/year (5-yr projection 275 MB; <1 GB soft limit).

**Follow-ups:**
- F/U-1: `data/articles/YYYY.json` dedup consolidation.
- F/U-2: Pagefind Korean stopwords tuning.
- F/U-3: Slack/email failure alerts (currently non-goal).
- F/U-4: Tab-specific editorial.md sections.
- F/U-5: Git LFS migration for archive JSON >2 years old.
- F/U-6: Delete `scripts/migrate_categories.py` 30 days after PR-1 merges.

---

## 7. Open Questions (persisted to `.omc/plans/open-questions.md`)

1. Does any external tool read `briefing.db` rows with legacy category names? Determines whether D10-B contingency activates.
2. Phase A0 observed cost ceiling: confirm `--max-cost-usd=1.5` default after measurement. Escalate if A0 >$0.80/day.
3. Playwright cold-cache install time on the team's GH Actions runner tier — if >120s, switch to F6b manual checklist.

---

*End of plan v2. Awaiting Architect + Critic re-review.*
