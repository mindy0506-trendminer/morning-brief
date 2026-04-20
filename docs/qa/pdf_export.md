# PDF Export Manual QA Checklist

**OQ9 resolution (2026-04-19):** We ship a manual QA checklist instead of a Playwright-automated test (F6b). Perform this checklist whenever `print.css` or the card/tab templates change.

Target browser: Chrome (latest), Firefox (latest), Safari (latest). Edge and mobile Safari are best-effort.

## How to trigger PDF export

1. Open the briefing page in a browser (e.g. `file:///D:/.../out/index.html` or the deployed URL).
2. Press `Ctrl+P` (Windows/Linux) or `Cmd+P` (macOS).
3. Destination: "Save as PDF".
4. Paper size: A4 (default).
5. Margins: Default.
6. Scale: 100%.
7. Background graphics: **ON** (to preserve tab badges).

## Checklist (run all in each browser)

### Layout
- [ ] Sidebar is hidden in the PDF
- [ ] Tab navigation bar is hidden (all 6 tabs are linearized vertically)
- [ ] Search bar is hidden
- [ ] Hamburger menu icon is hidden
- [ ] Header shows: `트렌드랩506 브리핑 YYYY-MM-DD` on every page
- [ ] Page margins look balanced (no cutoff text at edges)

### Content
- [ ] All 6 tabs are present in order: 거시매크로, F&B, 뷰티, 패션, 라이프스타일, 소비트렌드
- [ ] Each tab has a visible heading
- [ ] All 15 cards per tab are rendered (total 90 cards)
- [ ] Each card shows: headline (1 line), summary (up to 3 lines), source row, country indicator
- [ ] Original headline appears in source section in its original language (JA/ZH/ES characters render correctly)
- [ ] Hyperlinks are shown (URL visible in PDF form, e.g. `[원문](https://example.com)` or inline)
- [ ] MacroTab cards show SCTEEP badges (S/C/T/E/E/P chips) when applicable
- [ ] Non-MacroTab cards do NOT show SCTEEP badges
- [ ] Executive summary (오늘의 요약) appears at top
- [ ] Insight box (오늘의 인사이트) appears after all tabs

### Typography
- [ ] Korean text renders without mojibake (no boxes or question marks)
- [ ] Japanese (日本語) text renders correctly
- [ ] Chinese (中文) text renders correctly
- [ ] Spanish (Español) text renders correctly with diacritics
- [ ] Font sizes are readable (body ≥11pt, headline ≥14pt)
- [ ] No text is clipped by 3-line clamp on the PDF version (clamp should be disabled in print.css)

### Page breaks
- [ ] Tabs start on new pages (page-break-after on each tab section)
- [ ] No card is split across page boundaries
- [ ] No orphaned headings (e.g. a tab title at the bottom of a page with cards on next page)

### Branding
- [ ] 트렌드랩506 logo/text present in header
- [ ] Date is formatted as YYYY-MM-DD (not MM/DD/YYYY or locale-dependent)
- [ ] Partial-banner banner (if present) is prominently visible on first page

### Accessibility
- [ ] PDF contains searchable text (try Ctrl+F in the generated PDF)
- [ ] Links are clickable in the PDF (test one link from each tab)
- [ ] No image-based text (all content is selectable/copyable)

### Edge cases
- [ ] Day with <15 cards in some tabs still renders cleanly (empty slots should not show broken layout)
- [ ] Day with partial_banner renders banner at top, no content loss
- [ ] Cards with Korean-only source handle original_headline gracefully (either show Korean twice or hide the duplicate)

## When this fails

1. Inspect print styles: DevTools → Rendering → emulate print media.
2. Check `morning_brief/site/static/css/print.css` for the specific rule.
3. Rebuild the sample site: `python morning_brief.py run --renderer=site --dry-run`.
4. Re-open `out/index.html` and retry Ctrl+P.

If a fix requires non-trivial CSS changes, open a sub-ticket. Log the browser+version where the issue appeared.

## Sign-off

Each release must have at least one browser's checklist signed off. Record the result in release notes:

```
PDF QA 2026-MM-DD — Chrome 140 on Windows 11 — all pass — mindy
```
