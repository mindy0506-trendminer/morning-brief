# Deep Interview Spec: Morning Brief Web — 트렌드랩506 6탭 브리핑 사이트

## Metadata
- Interview ID: di-2026-04-19-morning-brief-web
- Rounds: 6
- Final Ambiguity Score: **7.9%**
- Type: **brownfield** (extends existing `morning_brief` Python CLI)
- Generated: 2026-04-19
- Threshold: 20% (met by round 5 at 15.2%, further refined in round 6)
- Status: **PASSED**
- Base directory: `D:/OneDrive/바탕 화면/클로드코드 비서만들기 연습/`

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.96 | 0.35 | 0.336 |
| Constraint Clarity | 0.85 | 0.25 | 0.2125 |
| Success Criteria | 0.92 | 0.25 | 0.230 |
| Context Clarity | 0.95 | 0.15 | 0.1425 |
| **Total Clarity** | | | **0.921** |
| **Ambiguity** | | | **0.079 (7.9%)** |

## Goal

기존 `morning_brief` Python CLI 파이프라인을 확장하여, **매일 아침 7시 GitHub Actions가 자동 실행**하여 **정적 HTML 웹사이트**로 배포되는 **6탭 뉴스 브리핑 서비스**를 구축한다. 웹사이트는 GitHub Pages(또는 Netlify)에 개인 공개 URL로 호스팅되며, 브라우저에서 반응형 UI로 탐색 가능하다.

**6탭 구조 (계층 분리):**
- **1 메타 탭**: `거시매크로(Macro Trends)` — SCTEEP 프레임워크 (Social, Culture, Technology, Economy, Environment, Politics) 기반 거시 흐름
- **5 산업 탭**: F&B, 뷰티, 패션, 라이프스타일, 소비트렌드

각 탭에 15개 뉴스 카드, 카드당 한국어 3줄 요약 + 원문 헤드라인(원어 보존) + 원문 하이퍼링크 + 국기/국가코드.

## Constraints

**배포·인프라:**
- 정적 사이트 호스팅 (GitHub Pages 또는 Netlify)
- GitHub Actions로 매일 07:00 KST 자동 빌드·배포
- 비용 0원 (호스팅 무료)
- Git repo가 아카이브 DB 역할 (HTML + JSON 커밋 누적)

**기술 스택:**
- 기존 `morning_brief` Python 3.11+ 파이프라인 유지
- Anthropic Claude (Haiku 클러스터링 + Sonnet 요약/선별)
- 정적 HTML 생성 (renderer.py 교체, Jinja2 유지 가능)
- 반응형 CSS (모바일 지원 필수)

**언어:**
- 소스 언어: 5개 (한국어·영어·일본어·중국어·스페인어) RSS 피드
- 출력 언어: **모든 헤드라인/요약은 한국어**
- 원문 헤드라인은 출처 섹션에 원어 그대로 보존

**선정 원칙 (자동 점수 가중치):**
- 다매체 동시 보도: 40% (24시간 이내 2개 이상 매체)
- 새로움: 30% (최근 30일 내 유사 뉴스 없음)
- 기업 태그: 30% (대기업·유통·혁신 스타트업)

**편집 관점:**
- 트렌드랩506 리서치 관점 반영
- `editorial.md` 파일로 Sonnet 프롬프트 관리 (운영 중 수정 가능)

## Non-Goals

- ❌ 인증/로그인 시스템 (URL 공개, 누구나 접근 가능하되 URL만 알면 됨)
- ❌ 댓글/소셜 기능
- ❌ SEO 최적화 (개인 공유 수준)
- ❌ 실시간 푸시 알림 (매일 1회 빌드)
- ❌ 동적 백엔드(API 서버) — 완전 정적
- ❌ 유료 피처 / 구독
- ❌ 타임라인 스크롤/무한 피드 UI (탭+카드 그리드 고정)
- ❌ AI 번역 품질 A/B 테스트 (단일 프롬프트로 진행)
- ❌ 모바일 네이티브 앱

## Acceptance Criteria

### 구조
- [ ] 웹사이트는 6개 탭으로 구성된다: `거시매크로` (첫 번째), `F&B`, `뷰티`, `패션`, `라이프스타일`, `소비트렌드`
- [ ] 각 탭에 정확히 15개의 뉴스 카드가 렌더링된다
- [ ] 거시매크로 탭은 SCTEEP 6차원 태그(S/C/T/E/E/P)를 카드별로 시각화한다

### 뉴스 카드
- [ ] 카드는 헤드라인 1줄 + 3줄 이내 한국어 요약 + 하단 출처 + 하이퍼링크로 구성된다
- [ ] 각 카드에 국가 표시(국기 또는 ISO-3166 alpha-3 괄호 안)가 포함된다
- [ ] 출처 섹션에는 **원문 헤드라인이 원어 그대로** 표시되고, 원문 링크가 연결된다

### 아카이브·네비게이션
- [ ] 왼쪽에 날짜별 네비게이션 사이드바가 존재한다
- [ ] 날짜는 연(年) > 월(月) > 일(日) 드롭다운 계층으로 확장된다
- [ ] 왼쪽 상단에 검색창이 위치하며 아카이브 전체에서 검색 가능하다
- [ ] 과거 날짜 페이지도 클릭으로 이동 가능하며 영구 URL을 가진다

### 반응형·내보내기
- [ ] 모바일(375px 이상)에서 탭과 카드가 가독성 있게 렌더링된다
- [ ] 현재 보고 있는 날짜의 브리핑을 PDF로 내보낼 수 있다

### 선정 품질
- [ ] 1단계 자동 점수 필터가 탭별 후보 Top 30을 선별한다(가중치 40/30/30)
- [ ] 2단계 Sonnet이 Top 30에서 최종 15개를 선정한다
- [ ] 선정 프롬프트는 `config/editorial.md`에 저장되어 코드 수정 없이 운영 조정 가능하다

### 기업 태깅
- [ ] `config/companies.txt`에 기업명과 태그(`대기업`/`유통`/`혁신스타트업`)가 관리된다
- [ ] collector가 기업명을 인식하여 카드에 태그를 부여한다

### 자동화·배포
- [ ] GitHub Actions가 매일 07:00 KST에 실행되어 브리핑을 생성한다
- [ ] 생성된 HTML + JSON은 Git 커밋으로 저장되어 아카이브가 된다
- [ ] 전체 빌드(수집→선정→요약→렌더) 시간이 10분 이내이다

### 다국어 소스
- [ ] `config/sources.yml`에 5개 언어(KO/EN/JA/ZH/ES) RSS 피드가 정의된다
- [ ] 언어별 최소 3개 피드, 총 15개 이상의 피드가 구성된다
- [ ] 언어 간 엔티티 매칭(동일 이슈 감지)이 기존 R6 교차언어 패턴으로 동작한다

### 테스트·품질
- [ ] 기존 82개 테스트 중 수집·선정·요약 관련 테스트는 계속 통과한다
- [ ] 새 HTML 렌더러에 대한 테스트가 추가된다 (6탭 구조, 15카드, 국가 표시, 링크 유효성)
- [ ] PDF 내보내기 성공 여부 테스트 포함

## Assumptions Exposed & Resolved

| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "STEEP"이 5개 산업과 같은 계층 카테고리 | Contrarian: STEEP은 메타 분석 프레임워크, 산업과 다른 계층 | STEEP+Culture = `SCTEEP` 프레임워크로 확장, "거시매크로" 단일 메타 탭 + 5 산업 탭으로 2계층 구조 명시 |
| 출력 언어가 소스 언어별로 혼재 | 가독성 저하, 사용자 피로 | 모든 요약은 한국어, 원문 헤드라인만 출처 섹션에 원어 보존 |
| 자체 호스팅/유료 서버 필요 | 비용과 운영 부담 | GitHub Pages + GitHub Actions로 비용 0원, 인증 불필요 |
| 선정을 LLM만으로 | 일일 비용 급증, 재현성 저하 | 자동 점수(40/30/30) Top30 → Sonnet Top15 하이브리드 |
| 처음부터 새 스택으로 재작성 | Simplifier: 기존 파이프라인이 이미 필요 요소 90% 구비 | `morning_brief` 확장: renderer만 교체, 기타 자산(collector/selector/summarizer/editorial.md) 재사용 |

## Technical Context

**기존 `morning_brief` 파이프라인 (재사용):**

| 모듈 | 역할 | 재사용 여부 |
|------|------|-------------|
| `collector.py` | RSS 수집 + R6 교차언어 엔티티 추출 | ✅ 재사용 (JA/ZH/ES 피드 추가만) |
| `selector.py` | novelty + diffusion 스코어링 | ✅ 재사용 + `CompanyTag` 가중치 추가 |
| `summarizer.py` | Haiku 클러스터링 → Sonnet 요약 | ✅ 재사용 + TwoStageSelector 논리 적용 |
| `models.py` | Pydantic 스키마 | ✅ 재사용 + `NewsCard`·`CompanyTag` 스키마 추가 |
| `renderer.py` | Jinja2 → `.eml` 출력 | ⚠ **교체**: 정적 HTML 사이트 생성기로 전면 재작성 |
| `config/sources.yml` | RSS 피드 정의 | ✅ 재사용 + 3개 언어 피드 추가 |
| `config/categories.yml` | 카테고리 키워드 | ✅ 재사용 + `MacroTab`, `ConsumerTrends` 추가, `Living` → `Lifestyle`, `Hospitality` deprecate 또는 Lifestyle에 흡수 |
| `config/brands.txt` | 기업 별칭 | ✅ 재사용 + `companies.txt`로 확장 (3-class 태그) |
| `config/editorial.md` | 편집 가이드 | ✅ 재사용 + Sonnet 선별 프롬프트 섹션 추가 |
| `briefing.db` (SQLite) | 로컬 히스토리 | 🔄 Git repo 아카이브로 대체, SQLite는 선별·중복제거 캐시로 유지 |
| 테스트 (82+) | 파이프라인 커버리지 | ✅ 80%+ 유지, renderer 테스트는 신규 작성 |

**신규 구성요소:**
- `renderer/site_generator.py` — 정적 HTML 사이트 생성기 (Jinja2 템플릿 + CSS)
- `renderer/templates/` — 6탭 레이아웃, 카드 컴포넌트, 날짜 네비게이션, 검색창
- `renderer/static/` — 반응형 CSS, 검색 JS (client-side Lunr.js 등)
- `config/companies.txt` — 기업명 + 태그(대기업/유통/혁신스타트업)
- `macro_pipeline.py` — SCTEEP 6차원 태깅 로직 (거시매크로 탭 전용)
- `pdf_export.py` — 브라우저 인쇄 스타일 또는 wkhtmltopdf/weasyprint 기반
- `.github/workflows/daily-brief.yml` — 매일 07:00 KST cron
- `archive/YYYY/MM/DD.html` + `archive/YYYY/MM/DD.json` — 누적 아카이브

**아키텍처 다이어그램:**

```
GitHub Actions (07:00 KST)
  ↓
morning_brief.cli run
  ├─ collector.py  (5언어 RSS → 원문 수집)
  ├─ selector.py   (novelty + diffusion + company_tag 가중치 점수)
  ├─ summarizer.py (Haiku 클러스터 → Sonnet 선별 Top15 + 한국어 3줄 요약)
  └─ renderer.site_generator
       ├─ 6탭 HTML (index.html + archive/YYYY/MM/DD.html)
       ├─ JSON sidecar (검색·PDF용)
       └─ search_index.json (Lunr.js)
  ↓
git add . && git commit && git push
  ↓
GitHub Pages 자동 재배포
```

## Ontology (Key Entities)

| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| NewsBriefing | core | date, tabs[6], generatedAt | has many CategoryTab, produces ArchiveEntry |
| MacroTab | core (meta layer) | name="거시매크로", sceepDimensions[6], cards[15] | has many NewsCard, tagged with SCTEEP |
| IndustryTab | core (5 instances) | name ∈ {F&B, 뷰티, 패션, 라이프스타일, 소비트렌드}, cards[15] | has many NewsCard |
| NewsCard | core | headlineKo(1줄), summaryKo(≤3줄), originalHeadline, sourceUrl, sourceName, countryCode, companyTag, publishedAt | belongs to Tab, has one OriginalHeadline, has one CountryIndicator |
| OriginalHeadline | supporting | textOriginal, language | embedded in NewsCard.source |
| CountryIndicator | supporting | iso3166Alpha3, flagEmoji | embedded in NewsCard |
| CompanyTaggingSystem | core | classes=[대기업, 유통, 혁신스타트업], configFile="companies.txt" | applies to NewsCard |
| TwoStageSelector | core | stage1=AutoScore(w={media:0.4, novelty:0.3, companyTag:0.3}, top=30), stage2=SonnetJudge(editorialPrompt, top=15) | reads RawArticles, writes NewsCard |
| EditorialPromptConfig | supporting | file="config/editorial.md", perspective="트렌드랩506" | consumed by TwoStageSelector |
| StaticSiteGenerator | core | templates, outputDir="site/", archiveStructure="archive/YYYY/MM/DD.html" | renders NewsBriefing |
| DateNavigator | supporting | hierarchy=[year, month, day], dropdownExpandable | renders in sidebar |
| SearchBar | supporting | position="top-left", scope="full-archive", engine="lunr.js" | queries SearchIndex |
| ArchiveDatabase | core | medium="Git repo", format="HTML+JSON per day" | accumulates NewsBriefing |
| PDFExport | supporting | trigger="button-per-page", engine="print-css or weasyprint" | exports current NewsBriefing |
| SCTEEP | core (framework) | dimensions=[Social, Culture, Technology, Economy, Environment, Politics] | tags each MacroTab card |
| TrendLab506 | stakeholder | perspective, editorialVoice | drives EditorialPromptConfig |

## Ontology Convergence

| Round | Entity Count | New | Changed | Stable | Stability Ratio | Notes |
|-------|-------------|-----|---------|--------|----------------|-------|
| 1 | 8 | 8 | - | - | N/A | 기본 구조 추출 |
| 2 | 9 | 1 (OriginalHeadline) | 1 (NewsCard 필드 확장) | 8 | 89% | 원문 헤드라인 보존 규칙 |
| 3 | 10 | 1 (StaticSiteGenerator) | 1 (ArchiveDatabase→Git) | 9 | 90% | 호스팅 결정 |
| 4 | 12 | 2 (MacroTab, SCTEEP) | 1 (CategoryTab→IndustryTab) | 9 | 83% | Contrarian: 계층 분리 |
| 5 | 16 | 4 (TwoStageSelector, CompanyTaggingSystem, EditorialPromptConfig, TrendLab506) | 0 | 12 | 75% | 선정 메커니즘 구체화 |
| 6 | 16 | 0 | 1 (STEEPPlusCulture→SCTEEP 정식 명칭) | 15 | 100% ✅ | **수렴** |

**수렴 판정:** Round 6에서 엔티티 신규 0개, 모든 변경은 명명 정규화. 두 라운드(5→6) 동안 핵심 개념 세트가 고정되어 온톨로지가 수렴했음.

## Interview Transcript

<details>
<summary>Full Q&A (6 rounds)</summary>

### Round 1 — Form factor
**Q:** 5개 언어 소스에서 수집한 뉴스의 출력 언어는?
**A:** 전부 한국어로 요약, 단 출처 섹션에는 원문 헤드라인을 원어 그대로 보존.
**Ambiguity after scoring:** (이 답변은 출력 형식 명세 전에 수신됨)

### Round 2 — Output language
**Q:** (Constraint Clarity 타겟) 5개 언어 소스 → 출력 언어 정책?
**A:** 모두 한국어. 출처에는 원문 헤드라인 보존.
**Ambiguity:** 38.5%

### Round 3 — Deployment
**Q:** (Constraint Clarity 타겟) 어디에 배포되고 누가 접근?
**A:** 개인 공개 URL — GitHub Pages/Netlify + GitHub Actions 매일 빌드.
**Ambiguity:** 29.8%

### Round 4 — Contrarian
**Q:** 🔥 STEEP이 F&B/뷰티와 동일 계층인가? (핵심 가정 도전)
**A:** STEEP은 별도 "거시매크로" 메타 탭으로, S·T·E·E·P + Culture 6차원 확장 프레임워크. 탭은 6개지만 계층은 1+5로 분리.
**Ambiguity:** 25.3%

### Round 5 — Selection mechanism
**Q:** 3원칙(다매체/새로움/기업태그) 기계화 방법?
**A:** 하이브리드. 1단계 자동 점수(40/30/30) Top30 → 2단계 Sonnet Top15. editorial.md로 선정 프롬프트 관리. companies.txt로 3-class 기업 태깅.
**Ambiguity:** 15.2% ✅

### Round 6 — Simplifier
**Q:** 🎯 기존 morning_brief 파이프라인 확장(renderer만 교체)이 최소 경로. 이 경로 선택?
**A:** 네. collector/selector/summarizer/editorial.md 재사용, renderer만 교체, MacroTab·5언어 피드·companies.txt·TwoStageSelector·DateNavigator·SearchBar·PDFExport·ArchiveDatabase 신규 추가, GitHub Pages+Actions. 기존 82 테스트 대부분 유지, renderer 신규 테스트 추가.
**Ambiguity:** 7.9% ✅

</details>
