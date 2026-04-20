# Open Questions

Tracks decisions deferred or items needing clarification across OMC plans.

## morning-briefing-plan-v1 — 2026-04-18
- [ ] OQ1: Subject-line format — keep `"[소비재 트렌드 조간] YYYY-MM-DD (Food/Beauty/Fashion/Living/Hospitality)"` or support A/B variants? — affects `renderer/eml_builder.py`, trivial either way.
- [ ] OQ2: Seed `config/brands.txt` with a ~50-brand starter list, or ship empty for user curation? — affects clustering quality for Fashion/Beauty; empty defaults reduce recall on duplicate detection.
- [ ] OQ3: Time zone for `generated_at` and "today" boundary — KST fixed (proposed) or local-machine? — default KST.
- [x] OQ4: ~~Slow-news-day fallback when a category has < 2 viable clusters — drop the section, show 1 item, or render "해당일 유의미한 이슈 없음" placeholder?~~ **RESOLVED in v2**: categories with <2 clusters after Call A do NOT placeholder or drop — their top items flow into a shared `misc_observations_ko` ("기타 관찰") bucket, capped at 3 items total. Subject line dynamically includes "기타 관찰" when present.
- [ ] OQ5: Provider abstraction — implement only Anthropic for Phase 1 (proposed), or wire GPT-4.1 as a second concrete backend from day 1? — abstraction point lives in `summarizer.py` regardless.

## morning-briefing-plan-v2 — 2026-04-18
- [ ] OQ6: Call A model choice — default Haiku 4 with escalation to Sonnet if AC8 live cross-lingual recall is <80% after first week. Confirm user is OK with this auto-escalation policy or prefers Haiku-only (cost-capped) / Sonnet-from-day-1 (quality-first) instead.

## morning-briefing-plan-v3 — 2026-04-18
- No new open questions introduced. v3 closes 3 Critic blockers + 6 recommended fixes over v2; OQ1/OQ2/OQ3/OQ5/OQ6 carry over unchanged. OQ4 remains resolved (misc "기타 관찰" bucket, formalized as the "category renders iff >=1 cluster at threshold" rule in v3 §5.4).

## morning-brief-web-plan-v2 — 2026-04-19
- [x] OQ7: ~~External `briefing.db` consumers?~~ **RESOLVED 2026-04-19**: No external consumers. **D10-A applies** — full rename + one-shot `scripts/migrate_categories.py` + delete `legacy_map`. Migration script deleted post-merge.
- [ ] OQ8: Phase A0 measured cost ceiling — after 3 dry-run baselines, confirm `--max-cost-usd=1.5` default holds. Escalate to user before Phase B if observed p95 > $0.80/day. (Still pending A0 measurement.)
- [x] OQ9: ~~Playwright cold-cache install time?~~ **RESOLVED 2026-04-19**: User elected **F6b manual QA checklist** (`docs/qa/pdf_export.md`) without measurement. Playwright dropped from `[dev]` extras. CI stays fast.
- [x] OQ10: ~~`macro_tagger.py` prompt authorship?~~ **RESOLVED 2026-04-19**: Hybrid — Planner writes SCTEEP few-shots **strictly grounded in established academic literature** (Aguilar PEST, Yuksel PESTEL, Hofstede cultural dimensions). **TrendLab506 subjective interpretation is FORBIDDEN** to preserve methodological reproducibility. User's review role is limited to verifying "did not deviate from standard definitions" — no subjective editorial adds. Prompt lives in **`config/macro_prompt.md`** (Option 3, separate file); `editorial.md` keeps only general editorial guidelines. Future edits require literature-citation comments.
- [x] OQ11: ~~Partial-build exit 6 behavior?~~ **RESOLVED 2026-04-19**: **Auto-retry (max 2 attempts, 10-min delay) then push-with-banner.** If both retries fail, still push `partial_banner.html`-annotated site. During retry window, site retains previous day's briefing (never goes empty).
