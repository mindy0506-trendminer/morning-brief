# Deep Interview Spec: Morning Consumer Trend Briefing (소비재 트렌드 조간 브리핑)

## Metadata
- Interview ID: deep-interview-morning-consumer-trend-briefing
- Rounds: 7
- Final Ambiguity Score: 19.5%
- Type: greenfield
- Generated: 2026-04-18
- Threshold: 20%
- Status: PASSED
- Challenge modes used: Contrarian (R4), Simplifier (R6)

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.85 | 0.40 | 0.340 |
| Constraint Clarity | 0.85 | 0.30 | 0.255 |
| Success Criteria | 0.70 | 0.30 | 0.210 |
| **Total Clarity** | | | **0.805** |
| **Ambiguity** | | | **0.195** |

## Goal
소비재 5개 산업(Food / Beauty / Fashion / Living & Lifestyle / Hospitality) 영역에서 **"소비자 변화"** 관련 뉴스를 매일 아침 수집·요약·선별하여, **1-3명의 본인/클라이언트에게 한국어 이메일 브리핑**을 생성한다. 브리핑은 본인이 한 번 검토한 뒤 직접 발송하는 **반자동(human-in-the-loop)** 구조이며, 향후 자동화 확장을 염두에 둔다.

핵심 차별점: 종합 시사 뉴스가 아니라, **소비재 5개 업종의 소비자 행동·트렌드 변화**에 특화된 편집 관점.

## Constraints
- **Input 언어**: 한국어 + 영어 혼합
- **Output 언어**: 한국어 (글로벌 원문 → LLM이 번역·요약을 동시에 처리)
- **뉴스 소스 범위**:
  - 국내 전통 매체 (네이버/다음/언론사)
  - 글로벌 전문 매체 (BoF, WWD, Vogue Business, Trendwatching 등)
  - 선별적 큐레이션 소스 (WGSN / Trendwatching처럼 이미 정리된 트렌드 리포트)
  - **제외**: Instagram, TikTok 등 SNS 플랫폼 직접 크롤링
- **배포 규모**: 1-3명 (본인 포함) — MVP는 소규모
- **배포 방식**: 로컬 스크립트 수동 실행 or 간단 스케줄러. 본인이 초안 검토 후 이메일 클라이언트에서 직접 발송 (또는 하위 수신자에게 일괄 발송)
- **개인화**: 없음. 전원 동일 메일 (범용성 우선)
- **발송 시점**: 아침 (정확한 시각은 사용자가 결정 가능)

## Non-Goals
- 종합 시사 뉴스 다이제스트 (정치·스포츠·일반 경제 등)
- Instagram / TikTok 등 플랫폼 크롤링·스크래핑
- 클라이언트별 개인화 브리핑
- 웹 대시보드 / 구독 관리 / 인증 시스템 (SaaS 플랫폼)
- 실시간 알림 (아침 1회 배치)
- 20명 이상 대규모 자동 발송 인프라

## Acceptance Criteria
- [ ] 매일 아침 1회 실행 시, 한국어+영어 소스에서 **소비재 5개 업종(Food/Beauty/Fashion/Living/Hospitality)** 관련 뉴스를 수집한다.
- [ ] 수집된 뉴스를 두 가지 기준으로 선별한다: **(1) 신규 트렌드·변화의 등장**, **(2) 반복·확산 정도(복수 매체 동시 언급)**
- [ ] 최종 이메일은 다음 **하이브리드 구조**로 생성된다:
  - 상단: 3줄 executive summary
  - 중단: 5개 카테고리별 섹션 (Food / Beauty / Fashion / Living / Hospitality), 카테고리마다 2-3개 이슈
  - 하단: 주간(또는 해당일) 인사이트 박스 (트렌드 해석·의미)
- [ ] 모든 Output 본문은 한국어로 작성된다 (원문 출처 링크는 영문 가능).
- [ ] 각 이슈에 원문 소스 링크와 간단 요약(1-3문장)이 포함된다.
- [ ] 본인이 실행 → 초안 확인 → 이메일로 발송하는 흐름이 수동이지만 원활하다 (copy-paste 최소화, 예: `.eml` 파일 생성 또는 Gmail 임시 저장함 자동 draft).
- [ ] 1일치 뉴스 수집·선별·요약·이메일 초안 생성 전 과정이 **10분 이내**에 완료된다 (수동 실행 기준).

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "오늘의 뉴스" = 종합 시사 뉴스 | R1: 클라이언트 정체는? | **소비재 5개 업종·소비자 변화 특화**로 범위 축소 |
| Instagram/TikTok 같은 소셜 플랫폼 크롤링 필요 | R4 Contrarian: 제외해도 가치 남나? | 플랫폼 크롤링 제외, **큐레이션된 트렌드 리포트 소스(WGSN/Trendwatching 류)만** 선별 포함 |
| 처음부터 자동화된 SaaS 필요 | R6 Simplifier: 최소 가치 버전? | **1-3명, 수동 검토 후 발송**으로 축소. 인프라 복잡도 제거 |
| 클라이언트별 개인화 브리핑 | R5: 선별 기준? | 사용자가 "범용성을 위해"라고 명시 → **전원 동일 메일** 결정 |
| 한국어 소스만 | R7: 입력 언어? | **한+영 혼합 input, 한국어 output** (LLM이 번역+요약 동시 처리) |
| "핵심 이슈"의 정의가 명확 | R5: 어떤 기준으로 5개 선별? | **신규성 + 반복·확산도** 두 축으로 확정 |

## Technical Context (권장 기술 선택)

> 기술 스택은 명시적으로 정해지지 않았으므로 아래는 MVP에 최적화된 **기본 권장안**입니다. 실행 단계(ralplan/autopilot)에서 조정 가능합니다.

- **런타임**: Python 3.11+ (뉴스 파싱·LLM 호출·이메일 생성에 성숙한 생태계)
- **LLM**: Claude Sonnet 4.6 or GPT-4.1 (다국어 요약 + 선별 로직)
  - 프롬프트 캐싱 활용 (카테고리 정의·편집 가이드를 시스템 프롬프트로 고정)
- **뉴스 수집**:
  - Google News RSS / Naver News RSS (카테고리 키워드 기반)
  - BoF·WWD·Vogue Business RSS
  - 필요 시 `feedparser` + `requests` + `BeautifulSoup`
- **이메일 초안**:
  - HTML 이메일 템플릿 (Jinja2)
  - Phase 1: `.eml` 파일 저장 → 사용자가 이메일 클라이언트에서 열어 발송
  - 또는 Gmail API로 "임시보관함 draft 생성" (수동 검토·발송)
- **실행 방식**:
  - Phase 1: CLI 스크립트 (`python morning_brief.py`)
  - Phase 2 (선택): macOS `launchd` / Windows `작업 스케줄러`로 아침 자동 실행

## Ontology (Key Entities)

| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| Client | core domain | id, name, email, industry_interest | Receives EmailBriefing |
| Industry | core domain | name (Food/Beauty/Fashion/Living/Hospitality) | Contains ConsumerTrendNews |
| ConsumerTrendNews | core domain | title, summary, source_url, language, published_at, industry, raw_text | Belongs to Industry, has NewsSource |
| NewsSource | supporting | name, type (TraditionalMedia / SpecializedMedia / CuratedTrendReport), url, language | Produces ConsumerTrendNews |
| KeyIssue | core domain | title, summary_ko, criteria_score (novelty + diffusion), source_articles[] | Derived from ConsumerTrendNews via SelectionCriteria |
| EmailBriefing | core domain | generated_at, exec_summary (3 lines), category_sections[Industry→KeyIssue[]], insight_box, recipients | Sent to Client |

**속성 (엔티티가 아닌 하위 설정):**
- SelectionCriteria: novelty + diffusion (반복·확산도)
- DeliveryMode: SemiAutomated_LocalHumanReview
- LanguagePipeline: input=ko+en, output=ko

## Ontology Convergence

| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1 | 5 | 5 | - | - | N/A (initial) |
| 2 | 5 | 0 | 0 | 5 | 100% |
| 3 | 6 | 1 (NewsSource) | 0 | 5 | 83% |
| 4 | 6 | 0 | 0 | 6 | 100% |
| 5 | 6 | 0 | 0 | 6 | 100% |
| 6 | 6 | 0 | 0 | 6 | 100% |
| 7 | 6 | 0 | 0 | 6 | 100% |

**수렴 해석**: NewsSource가 Round 3에서 추가된 뒤 4라운드 연속 동일 6개 엔티티 유지. 도메인 모델 완전 수렴.

## Interview Transcript

<details>
<summary>Full Q&A (7 rounds)</summary>

### Round 1 — Goal Clarity
**Q:** 이 뉴스 브리핑을 받는 '클라이언트'는 어떤 분들인가요?
**A:** 1번(B2B 산업 고객) + 4번(임원급)이 혼합. 다만 종합 시사보다는 **소비자 변화** 관련 요소. Food / Beauty / Fashion / Living & Lifestyle / Hospitality (소비재 분야).
**Ambiguity:** 70.5% (Goal: 0.55, Constraints: 0.15, Criteria: 0.10)

### Round 2 — Success Criteria
**Q:** 내일 아침 클라이언트가 이 메일을 열어본다면 어떤 구조·내용이어야 "이거다!" 싶을까요?
**A:** 하이브리드 (상단 3줄 요약 + 카테고리별 섹션 + 인사이트 박스)
**Ambiguity:** 56% (Goal: 0.65, Constraints: 0.15, Criteria: 0.45)

### Round 3 — Constraints
**Q:** 뉴스 선소 범위는? (언어/소스)
**A:** 소셜/인플루언서 포함
**Ambiguity:** 50% (Goal: 0.65, Constraints: 0.35, Criteria: 0.45)

### Round 4 — Constraints (🔄 Contrarian Mode)
**Q:** 반대로 — MVP에서 소셜/인플루언서를 완전히 뺀다면 가치가 얼마나 줄어들까?
**A:** 중간안: 선별적 소셜 (Trendwatching, WGSN 같은 정리된 소스만 포함, 플랫폼 크롤링 제외)
**Ambiguity:** 42% (Goal: 0.70, Constraints: 0.55, Criteria: 0.45)

### Round 5 — Success Criteria
**Q:** 100개 중 "핵심 이슈 5개"를 고르는 기준은?
**A:** 새로운 트렌드·변화의 등장 + 반복·확산 정도. 범용성 중시 (개인화 X).
**Ambiguity:** 29% (Goal: 0.80, Constraints: 0.60, Criteria: 0.70)

### Round 6 — Constraints (🔄 Simplifier Mode)
**Q:** 첫 버전에서 몇 명에게 어떻게 전송?
**A:** 본인만/1-3명, 수동 검토 후 발송
**Ambiguity:** 22.5% (Goal: 0.85, Constraints: 0.75, Criteria: 0.70)

### Round 7 — Constraints
**Q:** 입력 언어 / 출력 언어?
**A:** 입력: 한+영 혼합 / 출력: 한국어
**Ambiguity:** 19.5% ✅ (Goal: 0.85, Constraints: 0.85, Criteria: 0.70)

</details>
