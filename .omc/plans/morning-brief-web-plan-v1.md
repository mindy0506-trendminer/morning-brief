# Morning Brief Web — Implementation Plan v1

**Source spec:** `.omc/specs/deep-interview-morning-brief-web.md` (di-2026-04-19-morning-brief-web, 7.9% ambiguity, 100% ontology convergence)
**Mode:** Ralplan consensus — **SHORT** (brownfield extension; not `--deliberate`)
**Author:** Planner (stage 1 of Planner → Architect → Critic pipeline)
**Date:** 2026-04-19

---

## 1. RALPLAN-DR Summary

### 1.1 Principles (5)

1. **Reuse over rewrite.** 기존 `collector` / `selector` / `summarizer` 파이프라인(82 테스트 커버)은 유지; `renderer.py`만 교체. Round 6에서 사용자가 명시한 최소 경로.
2. **Git-as-DB.** 일자별 HTML+JSON을 commit으로 누적. 외부 DB/스토리지 없음 → 0원 호스팅 유지.
3. **Static-first, client-rich.** 모든 검색/탐색/PDF는 정적 에셋 + 브라우저에서 처리. 서버가 필요한 순간 GitHub Pages 무료 제약이 깨진다.
4. **Config-driven editorial.** 6탭 구조·기업 태그·선정 프롬프트는 `config/*`에 선언. 코드 배포 없이 운영 조정 가능.
5. **Additive schema, versioned.** `LLMBriefing.schema_version`을 v2 → v3로 올리면서 기존 카테고리(Food/Beauty/Fashion/Living/Hospitality)와 새 탭(MacroTrends/F&B/Beauty/Fashion/Lifestyle/ConsumerTrends)을 alias로 양립.

### 1.2 Decision Drivers (top 3)

1. **Zero-cost daily reproducibility.** GitHub Actions cron + Pages + Git은 무료이며 재현 가능. 다른 선택지는 즉시 탈락 기준.
2. **Preserve the 82-test safety net.** collector/selector/summarizer 재사용을 위해 스키마·경로·함수 시그니처는 가능한 한 호환. 교체 대상은 renderer 본문 + 카테고리 enum의 "alias 확장"만.
3. **Daily build ≤10 min end-to-end.** 5언어 × 15 피드 → Haiku cluster → Sonnet select Top15 × 6 tabs. 스테이지별 런타임·API 토큰 예산이 작업 설계를 제약.

### 1.3 10 Key Decision Points

For each: options → pick + rationale.

---

#### D1. Static HTML generator architecture

**Options:**
- **(A) Jinja2 + Python `site_generator.py`** — 기존 summarizer가 이미 Jinja2를 쓰고 있고 deps에 포함됨. `briefing.html.j2` 자산 일부 재활용 가능.
- (B) 11ty / Astro (Node.js) — 풍부한 정적 사이트 기능, 하지만 Node toolchain을 추가 설치·캐시해야 하고 GitHub Actions 빌드 시간 증가.
- (C) 순수 Python f-strings + 수작업 HTML — deps 최소지만 6탭/아카이브/부분 템플릿을 관리하기 어렵다.

**Pick: (A) Jinja2.** 기존 deps 재사용, 팀 스킬 일치, Python 파이프라인 내부에서 호출 가능. 11ty는 빌드 시간 ≤10분 목표 대비 오버킬.

**Template structure:**
```
morning_brief/site/
  templates/
    base.html            — <head>, 사이드바 shell, 검색 widget mount point
    index.html           — {% extends base %}, 오늘 날짜 6탭 렌더
    archive_day.html     — {% extends base %}, 특정 YYYY/MM/DD 6탭 렌더
    partials/
      tab_nav.html       — 6탭 네비게이션 (현재 탭 highlight)
      card.html          — NewsCard 1장 (헤드라인+3줄+국기+원문링크)
      macro_card.html    — SCTEEP 6-dimension pill 포함 variant
      sidebar_dates.html — 연>월>일 드롭다운
      search_widget.html — 검색 input + lunr/pagefind mount
  static/
    styles.css           — mobile-first 반응형 (375px+)
    print.css            — PDF 인쇄용 @media print
    search.js            — lunr.js init + UI
    pdf.js               — "PDF로 내보내기" 버튼 → window.print()
```

---

#### D2. MacroTab pipeline — separate or shared?

**Options:**
- (A) 완전 분리된 `macro_pipeline.py` — 별도 RSS 피드 세트(매크로 전용) + 별도 Top30→Top15 + SCTEEP 태깅.
- **(B) 공유 수집 + 라우팅 계층** — 기존 collector가 모든 아티클을 수집 → `macro_router.py`가 5산업 category가 아닌 아티클 또는 SCTEEP 키워드 매치 아티클을 MacroTab으로 분류 → SCTEEP 태깅은 **summarizer Call A의 Haiku 단계**에서 각 MacroTab 클러스터에 `sceep_dim` 라벨 추가.
- (C) 5산업과 동일 파이프라인이되 category="Macro"로 태깅 — SCTEEP 차원 없음.

**Pick: (B) 공유 수집 + Haiku 태깅.** Round 4에서 MacroTab은 메타 계층으로 확정 → 별도 피드보다는 "모든 수집물의 cross-industry 시사점"을 추출하는 편이 자연스러움. 비용도 단일 Haiku 호출 범위 내에서 해결.

**SCTEEP tagging 위치:** Call A (Haiku). `CallAClusterOut`에 optional `sceep_dimensions: list[Literal["S","C","T","E1","E2","P"]] | None` 필드 추가. IndustryTab 클러스터는 null, MacroTab 클러스터는 1–3개 차원 라벨.

---

#### D3. `companies.txt` schema

**Options:**
- (A) Plain TXT, `이름=canonical @tag` 형식 한 줄씩 (e.g., `쿠팡=Coupang @유통`). brands.txt 포맷 최소 확장.
- **(B) `config/companies.yml` YAML** — alias 다수, 다중 태그, 카테고리 hint 지원.
- (C) 기존 `brands.txt`에 `# @tag` 주석으로 태그 — 파서 복잡도 급증, 비추.

**Pick: (B) YAML.** `CompanyTag` enum(`대기업`/`유통`/`혁신스타트업`) + 다중 alias + category_hint가 필요하므로 TXT는 한계. 기존 `brands.txt`는 유지하되 collector가 **둘 다 로드**(brands.txt는 단순 alias 매핑 전용, companies.yml은 tag-bearing). 마이그레이션 유틸 1회 실행.

```yaml
# config/companies.yml
companies:
  - canonical: Coupang
    aliases: [쿠팡, coupang]
    tag: 유통
    category_hint: null  # any
  - canonical: Samsung
    aliases: [삼성, samsung]
    tag: 대기업
  - canonical: Oatly
    aliases: [오틀리, oatly]
    tag: 혁신스타트업
    category_hint: Food
```

**Consumer 경계:**
- `collector.ingest_entities()` → `article.company_tags: list[CompanyTag]` 채움 (새 필드).
- `selector.score_candidates()` → `CompanyTag` 매치 시 `company_tag_score = 1.0` 아니면 0.0. **selector가 읽는 주체**.

---

#### D4. Archive URL structure

**Options:**
- **(A) `archive/YYYY/MM/DD.html`** — 파일 1개/일. 간단, Git diff 작음, GH Pages의 directory listing 친화.
- (B) `archive/YYYY-MM-DD/index.html` — pretty URL (`/archive/2026-04-19/`), 디렉토리 수 폭발(연간 365개).
- (C) `?date=2026-04-19` 쿼리 — 정적 호스팅에서 JS로만 해석. SEO·공유 친화도 최악.

**Pick: (A) `archive/YYYY/MM/DD.html`.** Spec Technical Context에도 명시. 연간 디렉토리 13개(12 months + 1 year), 매년 추가. Permanent link = 파일 경로 그대로.

**Permanent link policy:** 한 번 커밋된 `archive/YYYY/MM/DD.html`은 **append-only, no-overwrite**. 재생성이 필요하면 `archive/YYYY/MM/DD.html` 옆에 `DD-revN.html`을 만들고 index에 cross-link.

---

#### D5. Search engine (5-lang)

**Options:**
- **(A) Pagefind** — 정적 사이트 친화, 다국어 네이티브, UI 번들 포함, 빌드 시간 짧음.
- (B) Lunr.js — 오래된 표준, 한국어/일본어/중국어 토크나이저 플러그인 필요, 토크나이저마다 index 별도.
- (C) 단순 `search_index.json` + 브라우저에서 substring grep — 5만 건 누적 아카이브에서는 성능/UX 부족.

**Pick: (A) Pagefind.** 다국어 CJK/Latin 토크나이징을 기본 지원, 빌드 시 HTML을 크롤링해 fragment index 생성 → JS 번들 크기 최적화(lazy load), GH Pages에 그대로 배포 가능. GH Actions에 `pagefind` CLI step 추가.

**5-lang 전략:** Pagefind `--root site/`로 전체 크롤. 각 HTML의 `<html lang="ko">` 기준 언어 분리 인덱스. 쿼리 시 언어 필터 선택 가능하되, 기본은 "전체 언어"(한국어 요약이 모든 카드에 있으므로 주 검색 히트는 KO).

---

#### D6. PDF export

**Options:**
- **(A) 브라우저 `window.print()` + `print.css` `@media print`** — zero-infra, 사용자 PC에서 실행.
- (B) `weasyprint` (Python, Actions에서 렌더 → `archive/YYYY/MM/DD.pdf` 커밋) — PDF가 Git에 누적되어 repo 크기 급증.
- (C) `wkhtmltopdf` — GH Actions에서 설치는 되지만 Qt deprecated, 유지보수 불확실.

**Pick: (A) 브라우저 print.** Non-goal에 "실시간 푸시/서버 의존성 없음" 원칙 → 사용자 요청 시에만 생성. Print CSS: 사이드바/검색 숨김, 탭을 각 페이지로 page-break, 링크는 footnote. PDF 파일을 Git에 누적하지 않음 → repo 크기 안정.

**AC 대응:** "현재 보고 있는 날짜의 브리핑을 PDF로 내보낼 수 있다" → "PDF 내보내기" 버튼이 `window.print()` 호출. E2E 테스트: Playwright headless에서 PDF 생성 → 페이지 수, PDF metadata 확인.

---

#### D7. GitHub Actions structure

**Options:**
- **(A) 단일 workflow `daily-brief.yml`** — Setup → Run pipeline → Build site → Deploy. 단순, 디버깅 쉬움.
- (B) 3분할 (collect → build → deploy) — 스테이지별 artifact 전달 복잡, 시간 오버헤드.
- (C) Reusable workflow + matrix — 5언어 병렬 수집. 현 규모에서는 과설계.

**Pick: (A) 단일 workflow.** 전체 빌드가 ≤10분이면 분할할 이유 없음. 실패 rollback = 마지막 commit push 차단(실패 시 push하지 않음). Secrets: `ANTHROPIC_API_KEY` (GH secret). 타임존: `TZ=Asia/Seoul` + cron을 `0 22 * * *` UTC (= 07:00 KST).

**실패 롤백:** GH Actions step에 `on-failure: exit without pushing`. Git 상태 미변경 = Pages 재배포 없음. Slack/이메일 알림은 non-goal이지만 Actions UI 실패 배지로 충분.

---

#### D8. Test compatibility

**Impact 분석 (82개 테스트):**

| 파일 | 테스트 수 (approx.) | 영향 |
|------|---------|------|
| `test_collector.py` | 7 | companies.yml 추가 로딩 로직만 신규, 기존 brands.txt 동작은 유지 → 영향 없음 |
| `test_selector.py` | 13 | `CompanyTag` 가중치가 추가되지만 기존 scoring path는 유지(회귀 방지용 파라미터 default=False) → 영향 없음 |
| `test_summarizer.py` | 42 | 카테고리 Literal 변경이 큼. 전략: **Literal을 확장**(Food,Beauty,Fashion,Living,Hospitality + FnB,Lifestyle,ConsumerTrends,MacroTrends). 마이그레이션 매핑 (Food↔F&B, Living↔Lifestyle, Hospitality→deprecated but accepted) → 기존 fixture 통과 |
| `test_renderer.py` | 25 | **전부 eml/subject/email-module 대상** → renderer 교체 시 **전수 제거**. 새 `test_site_generator.py`로 대체 |
| `test_ac_coverage.py` | 7 | AC5(source link dedup), AC7(run≤10min), AC11(eml parseable), AC12(feed 3개+), AC15(stage caps) → eml 관련(AC11) 교체, 나머지 유지 |
| `test_end_to_end_dry_run.py` | 2 | renderer 결과를 eml 대신 HTML site 구조로 assert하도록 갱신 |
| `test_models_forbid.py` | 3 | 새 필드는 forbid extra를 유지하도록 추가 케이스 필요 |
| `test_db_bootstrap.py` | 1 | 영향 없음 |

**결과:** 82개 중 약 **28개가 교체**(renderer 25 + AC11 + end-to-end 2), **54개는 그대로 통과**. 신규 30개 테스트 추가(site generator, search, pdf, SCTEEP, CompanyTag).

**전략:** `renderer.py`는 **유지** (deprecated 표시) → `test_renderer.py`는 skip/xfail로 처리하지 않고 **1번의 큰 커밋으로 삭제**. 새 `morning_brief/site/site_generator.py`로 대체, CLI에 `--renderer={eml,site}` 플래그로 점진적 전환 기간 제공(1주).

---

#### D9. Daily cost cap

**Estimate:**
- 수집: 15 피드 × 평균 20 엔트리 = 300 raw articles.
- precluster → 6 tabs × ~50 candidates = 300 candidates.
- **Call A (Haiku)**: 6 tabs × 50 candidates → batch. Input ~30k tokens, output ~5k tokens. Haiku @ $0.25/$1.25 per MTok = **~$0.014**.
- **Call B (Sonnet)**: 6 tabs × Top30→Top15 선별 + 한국어 3줄 요약. Input ~60k tokens (기사 enriched_text 포함), output ~15k tokens (15 cards × 6 tabs × ~150 tokens). Sonnet 4.6 @ $3/$15 per MTok = **~$0.405**.
- **일일 합계 ≈ $0.42 / 일 ≈ $12.6 / 월**.

**Cap mechanism:**
- CLI flag `--max-cost-usd=1.0` (default 1.0). `LLMClient`에서 누적 토큰 추적 → 초과 시 SystemExit(5).
- Actions workflow에 `continue-on-error: false` + daily cost 로그를 `archive/YYYY/MM/DD.json`에 기록.

**Sonnet token budget cap:** Top30→Top15 선별 프롬프트에서 각 candidate당 enriched_text를 500 char로 truncate. 비용 선형 증가 방지.

---

#### D10. `categories.yml` migration

**Options:**
- **(A) Alias expansion with backward-compat** — `Food` 키는 유지하되 `aliases: [F&B, FnB]` 추가. `Living` → `Lifestyle` alias. `Hospitality` → **deprecated, Lifestyle에 흡수**(spec Technical Context 명시). `ConsumerTrends`, `MacroTrends` 신규.
- (B) 완전 rename (Food→F&B, Living→Lifestyle, Hospitality 삭제) — 기존 42 summarizer 테스트 전부 깨짐.
- (C) 별도 `categories_v2.yml` 신규 파일, 기존 유지 — 두 체계가 공존 → 혼란.

**Pick: (A) Alias expansion.** 기존 Literal을 확장하면서 카테고리 매핑 테이블을 `config/categories.yml`의 `legacy_map:` 섹션에 선언.

```yaml
categories:
  MacroTrends:
    keywords: [거시, macro, steep, trend, 트렌드]
    sceep_enabled: true
  F&B:
    aliases: [Food, FnB]
    keywords: [식품, food, ...]
  Beauty:
    keywords: [...]
  Fashion:
    keywords: [...]
  Lifestyle:
    aliases: [Living]
    absorbs: [Hospitality]  # Hospitality 키워드도 여기에 merge
    keywords: [리빙, 라이프스타일, 여행, hotel, ...]
  ConsumerTrends:
    keywords: [소비, 구매, retail, consumer, ...]

legacy_map:
  Food: F&B
  Living: Lifestyle
  Hospitality: Lifestyle
```

`collector._assign_category()`와 `summarizer._CATEGORIES`는 **canonical 이름**(MacroTrends/F&B/Beauty/Fashion/Lifestyle/ConsumerTrends)을 쓰되, `legacy_map`을 통해 fixture와 기존 DB의 Food/Living/Hospitality 레코드를 자동 매핑.

---

## 2. Detailed Implementation Plan — File by File

### Phase A: Foundation (S–M)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| A1 | `config/companies.yml` (new) | D3 YAML schema. 초기 100개 기업 (brands.txt 44개 + 추가 56개: 유통·혁신 스타트업). | none | M |
| A2 | `config/categories.yml` (modify) | D10 alias + legacy_map 추가. MacroTrends, ConsumerTrends 섹션 신규. | A1 | S |
| A3 | `config/sources.yml` (modify) | JA/ZH/ES 피드 각 3+개 추가 (Google News 언어별 search feed + 현지 전문지). 총 15+ 피드 확보. | none | S |
| A4 | `config/editorial.md` (modify) | SCTEEP 라벨링 가이드 + Top30→Top15 선별 프롬프트 섹션 추가. | none | S |
| A5 | `morning_brief/models.py` (modify) | (i) `CompanyTag` enum (`대기업`/`유통`/`혁신스타트업`), (ii) `Article.company_tags: list[CompanyTag]`, (iii) Category Literal 확장, (iv) `NewsCard`·`SceepDimension`·`MacroCard` 신규, (v) `LLMBriefing.schema_version: Literal["v3"]`, (vi) `CallAClusterOut.sceep_dimensions` optional 필드. | A1, A2 | M |
| A6 | `morning_brief/db.py` (modify) | `articles.company_tags` JSON 컬럼 추가 (bootstrap migration). 기존 rows는 `[]` 디폴트. | A5 | S |

**AC coverage in Phase A:** 기업 태깅(AC `companies.txt`), 다국어 소스(AC `sources.yml`), 선정 품질(AC `editorial.md`).

### Phase B: Pipeline extensions (M)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| B1 | `morning_brief/collector.py` | `load_companies()` 함수 추가, `ingest_entities`에서 `article.company_tags` 채움. JA/ZH/ES 엔티티 추출 regex 확장 (R6 cross-lingual). 기존 `load_brands()` 유지. | A1, A5 | M |
| B2 | `morning_brief/selector.py` | `score_candidates()`에 `company_tag_score` 추가. 점수 공식을 spec 가중치에 맞춤: **combined = 0.4×diffusion + 0.3×novelty + 0.3×company_tag_score** (Round 5 확정). Backward compat: `use_company_tag=False` 파라미터로 기존 호출자는 구 공식 사용. | A5, B1 | M |
| B3 | `morning_brief/two_stage_selector.py` (new) | `TwoStageSelector`: stage1=auto score Top30 per tab, stage2=Sonnet judge via `editorial.md` prompt → Top15. summarizer.run_summarizer()가 call_b 전에 호출. | B2, A4 | M |
| B4 | `morning_brief/macro_router.py` (new) | 모든 클러스터를 순회 → SCTEEP 키워드/Sonnet 판정으로 MacroTab 후보 선별. Call A 결과에 `sceep_dimensions`가 있으면 사용. | A5 | M |
| B5 | `morning_brief/summarizer.py` | `_CATEGORIES`를 6탭 canonical 이름으로 변경, legacy_map 통한 migration 지원. Call A 프롬프트에 SCTEEP dimension 지시 추가. TwoStageSelector 통합. | A4, A5, B3, B4 | M |

**AC coverage in Phase B:** 선정 품질(1단계 Top30/2단계 Top15, 가중치 40/30/30), 기업 태깅(collector 인식 + 카드 부여), SCTEEP 태깅.

### Phase C: Static site generator (L)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| C1 | `morning_brief/site/__init__.py` (new) | Package marker. | none | S |
| C2 | `morning_brief/site/site_generator.py` (new) | `build_site(briefing: NewsBriefing, today, out_dir: Path)` → `index.html`, `archive/YYYY/MM/DD.html`, `data/YYYY/MM/DD.json`. 기존 `renderer.build_render_context()`를 `build_news_briefing()`으로 대체 (cluster → NewsCard 변환 + SCTEEP + CompanyTag 포함). | Phase B | L |
| C3 | `morning_brief/site/templates/base.html` (new) | `<head>` 메타, 반응형 viewport, Pagefind JS mount, 사이드바 shell, "PDF 내보내기" 버튼. | C2 | M |
| C4 | `morning_brief/site/templates/index.html` (new) | 오늘 날짜. 6탭 nav + default 첫 탭(거시매크로) 활성. | C3 | S |
| C5 | `morning_brief/site/templates/archive_day.html` (new) | 특정 날짜. index와 거의 동일, nav에 "오늘로 돌아가기" 링크. | C3 | S |
| C6 | `morning_brief/site/templates/partials/{tab_nav,card,macro_card,sidebar_dates,search_widget}.html` (new) | 6개 partial. `card.html`: 헤드라인 1줄 + 3줄 요약 + 출처 섹션(원문 헤드라인 원어 + 링크) + 국기(ISO3166) + CompanyTag pill. `macro_card.html`: card + SCTEEP 6 pill 가시화. | C3 | M |
| C7 | `morning_brief/site/static/styles.css` (new) | Mobile-first (375px+). 6탭 grid, card layout, 사이드바, 검색창. | C3 | M |
| C8 | `morning_brief/site/static/print.css` (new) | `@media print`: 사이드바·검색·nav 숨김, 탭별 page-break, 링크 footnote. | C7 | S |
| C9 | `morning_brief/site/static/pdf.js` (new) | "PDF 내보내기" 버튼 click → `window.print()`. | C3 | S |
| C10 | `morning_brief/site/flags.py` (new) | `country_to_iso3166(source_lang, url_tld) → (alpha3, flag_emoji)` 유틸. | none | S |
| C11 | `morning_brief/cli.py` (modify) | `_run_pipeline`: renderer 호출을 `site_generator.build_site()`로 교체. `--renderer={eml,site}` 플래그 (default `site`, `eml`은 deprecated). | C2 | S |

**AC coverage in Phase C:** 구조(6탭 + 15카드 + MacroTab SCTEEP), 뉴스카드(헤드라인+3줄+출처+링크+국기+원문보존), 반응형(375px+).

### Phase D: Aggregation & archive (M)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| D1 | `morning_brief/site/archive_indexer.py` (new) | `site/` 아래 `archive/YYYY/MM/DD.html` 스캔 → `data/archive_index.json` (date → title/summary snippet). 사이드바 드롭다운이 이 JSON을 읽어 클라이언트 렌더. | C2 | M |
| D2 | `morning_brief/site/templates/partials/sidebar_dates.html` (modify) | Year > Month > Day 3단 드롭다운. `archive_index.json`를 fetch해 JS로 트리 구성. | D1, C6 | M |
| D3 | `morning_brief/site/search_indexer.py` (new) | GH Actions에서 `pagefind --site site/` 실행 step을 호출하는 thin wrapper. Python이 직접 tokenize 안 함 (Pagefind CLI에 위임). | C2 | S |
| D4 | `morning_brief/site/search_widget` template integration | `partials/search_widget.html`이 Pagefind UI bundle (`<script src="/pagefind/pagefind-ui.js">`) 로드. | D3 | S |
| D5 | `morning_brief/site/site_generator.py` (modify) | 빌드 끝에 archive index + sitemap 재생성. permanent URL 계약: 생성된 파일은 overwrite 금지(mtime 체크 → `DD-revN.html`). | C2, D1 | S |

**AC coverage in Phase D:** 아카이브·네비게이션(왼쪽 사이드바, 연/월/일 드롭다운, 전체 아카이브 검색, 영구 URL).

### Phase E: CI/CD (M)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| E1 | `.github/workflows/daily-brief.yml` (new) | cron `0 22 * * *` UTC (=07:00 KST). Steps: checkout → setup Python 3.11 → `pip install -e .[dev]` → install pagefind CLI → `TZ=Asia/Seoul morning-brief run` → `pagefind --site site/` → `git add site/ archive/ && git commit -m "auto-brief YYYY-MM-DD" && git push` → `actions/deploy-pages@v4`. | C11, D3 | M |
| E2 | `.github/workflows/pages-deploy.yml` (new) | `on: push: branches: [main]`, `paths: [site/**, archive/**]`. `peaceiris/actions-gh-pages@v4` 또는 GitHub native Pages from branch. | E1 | S |
| E3 | Repo settings | Secret `ANTHROPIC_API_KEY` 설정, Pages source = `gh-pages` branch OR `main:/site`. | E1 | S |
| E4 | `morning_brief/cli.py` (modify) | `--max-cost-usd` 플래그 (D9). 초과 시 SystemExit(5). 비용 로그 `archive/YYYY/MM/DD.json`에 기록. | Phase B | S |

**AC coverage in Phase E:** 자동화·배포(매일 07 KST + Git 커밋 아카이브 + 10분 이내).

### Phase F: Test harness (M)

| # | Files | Change | Deps | Size |
|---|-------|--------|------|------|
| F1 | `tests/test_renderer.py` (delete) | eml 기반 테스트 전체 제거. | C11 | — |
| F2 | `tests/test_site_generator.py` (new) | 6탭 구조, 탭당 15카드, 국가 표시, 링크 유효성, SCTEEP pill, CompanyTag pill, mobile viewport (BeautifulSoup HTML assertion). | C2 | L |
| F3 | `tests/test_macro_router.py` (new) | SCTEEP 분류 정확도, MacroTab 중복 방지. | B4 | M |
| F4 | `tests/test_two_stage_selector.py` (new) | Top30→Top15 로직, 가중치 40/30/30 검증 (fixture score → 선별 결과). | B3 | M |
| F5 | `tests/test_companies_tagging.py` (new) | companies.yml 로딩 + alias 매칭 + tag 부여 + legacy brands.txt 호환. | B1 | M |
| F6 | `tests/test_ac_coverage.py` (modify) | AC11(eml) 삭제, AC_PDF_EXPORT(신규) 추가: Playwright headless PDF 생성 테스트. AC_ARCHIVE_URL 추가. | E1 | M |
| F7 | `tests/test_end_to_end_dry_run.py` (modify) | renderer 대신 site_generator 결과 검증. `site/index.html`, `archive/2026/04/18.html`, `data/archive_index.json` 생성 확인. | C11 | M |
| F8 | `tests/fixtures/` (new files) | `macro_cluster_sample.json`, `companies_tagging_sample.json`, `multilang_articles_ja_zh_es.json`. | A5 | M |
| F9 | `tests/test_search_indexer.py` (new) | Pagefind CLI 호출은 mock. 결과 디렉토리 구조만 검증. | D3 | S |

**AC coverage in Phase F:** 테스트·품질(기존 82 테스트 중 54 유지 + PDF 내보내기 테스트 + 6탭/15카드/국가/링크 검증).

---

## 3. Acceptance Criteria Mapping

| Spec AC | Implemented by |
|---------|----------------|
| 웹사이트는 6개 탭으로 구성 (거시매크로 첫 번째) | C4, C6 (`tab_nav.html`), C11 (`--renderer=site`) |
| 각 탭에 정확히 15개 뉴스 카드 | B3 (TwoStageSelector Top15), F2 |
| 거시매크로 탭이 SCTEEP 6차원 태그를 카드별 시각화 | B4 (`macro_router`), C6 (`macro_card.html`), C7 (pill CSS) |
| 카드 = 헤드라인1줄 + 3줄 요약 + 출처 + 링크 | C6 (`card.html`), A5 (NewsCard schema) |
| 각 카드 국가 표시 (국기 또는 ISO3166 alpha3) | C10 (`flags.py`), C6 |
| 출처 섹션에 원문 헤드라인 원어 + 원문 링크 | A5 (`OriginalHeadline`), C6 |
| 왼쪽 날짜 네비게이션 사이드바 | C6 (`sidebar_dates.html`), D2 |
| 연>월>일 드롭다운 | D1 (archive_indexer), D2 |
| 왼쪽 상단 검색창 + 아카이브 전체 검색 | D3 (Pagefind), D4 |
| 과거 날짜 영구 URL | D5 (no-overwrite policy), C5 |
| 모바일 375px 이상 가독성 | C7 (mobile-first), F2 (viewport assertion) |
| 현재 날짜 PDF 내보내기 | C8 (print.css), C9 (pdf.js), F6 (Playwright PDF 테스트) |
| 1단계 Top30 가중치 40/30/30 | B2 (score_candidates), B3 (stage1) |
| 2단계 Sonnet Top15 | B3 (stage2), F4 |
| 선정 프롬프트 editorial.md 저장 | A4, B3 |
| companies.txt로 3-class 태그 관리 | A1 (YAML), B1 (load_companies) |
| collector 기업명 인식 + 카드 태그 | B1, F5 |
| GH Actions 매일 07 KST 실행 | E1 (cron `0 22 * * *` + TZ) |
| HTML + JSON commit 아카이브 | E1 (git add/commit/push step) |
| 전체 빌드 10분 이내 | E1 (log stage durations), D9 (cost cap = time cap proxy) |
| sources.yml 5개 언어 RSS | A3 |
| 언어별 최소 3피드, 총 15+ | A3 |
| 언어 간 엔티티 매칭 (R6 cross-lingual) | B1 (regex 확장), 기존 `collector.extract_entities` 유지 |
| 기존 82 테스트 중 수집·선정·요약 테스트 통과 | D8 전략 (54개 유지), F7 (end-to-end 갱신) |
| 새 HTML 렌더러 테스트 (6탭/15카드/국가/링크) | F2 |
| PDF 내보내기 성공 테스트 | F6 |

**모든 AC가 구현 단계에 매핑됨.**

---

## 4. Risk Callouts

1. **Jinja2 template sprawl.** 6탭 × 2 page types × partials → 15+ template. 완화: `partials/card.html`를 단일 소스 진실(SST)로 만들고 MacroTab은 variant(extends)로만 확장. 테스트에서 duplicate-render 감지.
2. **Git repo size growth.** 일 1 HTML(~100KB) + 1 JSON(~50KB) = 연 ~55MB. 5년 누적 275MB → 여전히 GitHub repo limit(1GB soft) 아래. **완화:** `archive/` 외 static 에셋(styles.css, search.js)은 content-hash 한 번만 커밋. JSON 내부 중복(기사 bundle)은 `id` 참조 + `data/articles/YYYY.json` 합본 전략 고려 (Phase G 후속 작업, 현 플랜 out of scope).
3. **API cost spike on 5-lang.** $0.42/일 추정 → 기사 수 2x 증가 시 $0.84. **완화:** D9의 `--max-cost-usd=1.0` cap + Call B 입력 truncate.
4. **Timezone handling.** GitHub Actions는 UTC 고정. cron `0 22 * * *` = 07:00 KST 평시 / 07:00 KST DST 영향 없음(KST는 DST 없음). `TZ=Asia/Seoul` 설정으로 Python `datetime.now()`는 KST 기준. 검증: `test_ac_coverage.py`에 timezone 계약 테스트 추가.
5. **Search index bloat over years.** Pagefind fragment 인덱스는 ~HTML의 20%. 연 55MB → 인덱스 11MB. 5년 누적 55MB 인덱스 → lazy load로 첫 검색 시에만 로드. **완화:** 인덱스를 `/pagefind/` 경로로 분리 → Pages CDN 캐시.
6. **Renderer replacement breaking eml-based tests.** D8 분석에서 28개 영향. **완화:** renderer.py를 `renderer_legacy.py`로 rename + 1주간 `--renderer=eml`로 fallback 유지. 테스트 교체는 1 PR로 atomic.
7. **Pagefind CJK 토큰화 품질.** 한국어 어간 분석 미흡 가능. **완화:** 릴리스 후 2주간 검색 쿼리 로그(Actions 아님, 클라이언트 localStorage) 기반으로 custom stopwords 튜닝. (현 플랜 out of scope)
8. **Backward-compat Literal 확장 실패.** Pydantic Literal은 strict. 확장 시 기존 fixture(Food/Beauty/...)도 자동 통과하려면 union 필요. **완화:** `Category = Literal["Food","Beauty","Fashion","Living","Hospitality","MacroTrends","F&B","Lifestyle","ConsumerTrends"]` 로 9-way union, legacy_map으로 출력 시 canonical로 정규화. `test_models_forbid.py`에 전체 enum 회귀 케이스.

---

## 5. Non-Goals Reminder (from spec §Non-Goals)

다음은 본 플랜 범위 **외**이며, Architect/Critic 리뷰 시 범위 크리프 여부 판단 기준:

- 인증/로그인 시스템 (URL 공개, 누구나 접근 가능)
- 댓글/소셜 기능
- SEO 최적화 (개인 공유 수준)
- 실시간 푸시 알림 (일 1회 빌드만)
- 동적 백엔드/API 서버 (완전 정적)
- 유료 피처 / 구독
- 타임라인 스크롤 / 무한 피드 UI (탭+카드 그리드 고정)
- AI 번역 품질 A/B 테스트 (단일 프롬프트)
- 모바일 네이티브 앱

**Planner self-check:** 위 어느 항목도 Phase A–F에 포함되지 않았음. 특히 Phase E의 GH Actions는 "빌드 + 커밋 + 배포"만 수행, 알림·모니터링 확장 없음.

---

## 6. ADR (Architectural Decision Record)

**Decision:** 기존 `morning_brief` Python CLI 파이프라인을 보존한 채 `renderer.py`만 정적 사이트 생성기로 교체하고, GitHub Pages + GitHub Actions로 일 1회 빌드·배포하는 6탭(1 매크로 + 5 산업) 정적 HTML 브리핑 서비스를 구축한다.

**Decision Drivers:**
1. 0원 호스팅 및 재현 가능한 일일 빌드 ≤10분
2. 기존 82 테스트 중 54개 커버리지 보존
3. 5언어 수집 × 6탭 × Top15 구조에서 일 $0.42 이하 API 비용

**Alternatives considered:**
- **완전 새 스택 (Node/11ty/Astro)**: 기존 42개 summarizer 테스트와 Jinja2·Pydantic 투자 폐기. Rejected — Round 6 Simplifier에서 명시적으로 기각됨.
- **MacroTab을 별도 파이프라인으로 분리**: 수집 RSS + collector + selector 중복 작성. Rejected — 공유 수집 + Call A 태깅이 비용·복잡도 모두 우수.
- **Lunr.js 검색**: 오래된 표준이지만 CJK 토크나이저 부족, 다국어 인덱스 관리 복잡. Rejected in favor of Pagefind.
- **서버사이드 PDF (weasyprint)**: Git repo에 PDF 누적 → 용량 폭발. Rejected — 브라우저 print로 zero-storage 대안 선택.
- **카테고리 완전 rename**: 42 테스트 즉시 깨짐. Rejected — alias + legacy_map 확장으로 backward-compat 유지.

**Why chosen:** 원 사용자 요구(0원, 재현성, 편집 가능성)를 만족하면서 기존 자산의 90%를 재사용. 6탭 구조는 ontology Round 4–6 수렴 결과 직접 반영.

**Consequences:**
- (+) 기존 파이프라인 안정성 유지 + 정적 사이트 배포로 호스팅 비용 0.
- (+) Git 이력 자체가 아카이브 DB, 별도 스토리지 없이 감사·롤백 가능.
- (+) editorial.md/companies.yml/categories.yml로 운영 조정이 코드 배포 없이 가능.
- (−) Literal enum 확장으로 legacy 카테고리와 canonical 카테고리 이중 관리 필요.
- (−) renderer.py 교체 과정에서 eml 기반 테스트 25개 폐기 (필연적 breaking change).
- (−) Git repo가 시간이 지날수록 누적 — 5년 후 ~275MB 예상 (GitHub 제한 내).
- (−) Pagefind CJK 토큰화가 완벽하지 않을 수 있음 — 후속 튜닝 필요.

**Follow-ups (out of scope of this plan, logged for later):**
- F/U-1: 아카이브 JSON 정규화 (기사 중복 제거 `data/articles/YYYY.json`).
- F/U-2: Pagefind 한국어 stopwords 튜닝.
- F/U-3: Actions 실패 시 Slack/이메일 알림(현재 non-goal이나 추후 옵션).
- F/U-4: `editorial.md`를 탭별 섹션으로 분리하여 탭마다 다른 편집 관점 부여.
- F/U-5: `archive/` 용량 관리 정책 (e.g., 5년 이상 된 `data/` JSON을 LFS로 이관).

---

*End of plan v1. Awaiting Architect steelman.*
