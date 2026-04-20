# Ralplan Consensus Seal — morning-brief-web

**Status:** ✅ APPROVED
**Date:** 2026-04-19
**Iterations:** 1/5
**Approved plan:** `.omc/plans/morning-brief-web-plan-v2.md`
**Source spec:** `.omc/specs/deep-interview-morning-brief-web.md` (Deep Interview, 7.9% ambiguity, 100% ontology convergence)

## Consensus summary

| Gate | Verdict |
|---|---|
| Planner v2 | Plan produced with CHANGELOG + RALPLAN-DR + ADR |
| Architect v2 | PASS — All A1–A8 non-negotiables satisfied |
| Critic v2 | APPROVE — 26/26 Acceptance Criteria mapped to plan steps + tests |

## Hard prerequisites before PR-1

1. **Phase A0 cost measurement** — Run `morning_brief run --dry-run` 3x, extract token counts, compute observed p95, set `--max-cost-usd` cap to 2.5× p95 in `daily-brief.yml`. If p95 > $0.80, escalate to user before Phase B.
2. **Resolve open questions** (see `open-questions.md`):
   - OQ7: External consumers of legacy categories
   - OQ8: Cost escalation trigger threshold
   - OQ9: Playwright vs manual PDF QA
   - OQ10: editorial.md prompt authorship
   - OQ11: Exit-code-6 push vs abort policy

## Autopilot handoff

Autopilot should:
- **Skip Phase 0 (Expansion)** — Spec already written by Deep Interview
- **Skip Phase 1 (Planning)** — Plan already consensus-approved
- **Start at Phase 2 (Execution)** — Implement v2 plan in 5-PR sequence
- **Phase 3 (QA)** — Run 83-test suite + F10–F16 new tests
- **Phase 4 (Validation)** — Verify all 26 AC satisfied
- **Phase 5 (Cleanup)** — Delete legacy renderer, finalize deploy

## Follow-ups (non-blocking)

- F/U-7: Tag `pre-renderer-deletion` at PR-4 parent commit for easy rollback
- F/U-8: Explicit unit test for MacroTab candidate routing into `macro_tagger.py`
- F/U-9: Execution note — run A6 schema bootstrap before A7 migration on fresh DBs
- F/U-10: Document Pagefind quality gate (seeded cross-language queries) in Phase F
