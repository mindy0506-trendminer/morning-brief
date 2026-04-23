# sources.yml 개편 제안서 (승인 대기)

생성: 2026-04-21
승인 대상: 슈퍼민디
정책: 사용자 승인 후에만 sources.yml 수정 + 커밋

---

## A. 현재 상태 감사 결과

- **전체 24개 피드 중 11개 살아있음, 11개 죽어있음 (50% 실패율)**
- 일본어(JA) · 스페인어(ES) 피드 0개 생존 → 다국어 브리핑 컨셉 깨진 상태
- 사용자 선호 한국 매체 4개 중 2개만 RSS 노출 (패션비즈 · 어패럴뉴스는 RSS 엔드포인트 없음)

---

## B. 제거 대상 (11개, 주석 처리)

주석으로 보존하여 향후 RSS 복구 시 참고 가능:

| 이름 | URL | 언어 | 에러 | 처방 |
|---|---|---|---|---|
| Vogue Business | www.voguebusiness.com/rss | en | 404 | 주석 처리 |
| Hospitality Net | www.hospitalitynet.org/... | en | 404 | 주석 처리 |
| TrendWatching | www.trendwatching.com/feed/ | en | 404 | 주석 처리 (사용자 사전 인지) |
| Springwise | www.springwise.com/feed/ | en | 403 | 주석 처리 (Cloudflare) |
| Nikkei Business RSS | www.nikkei.com/rss/topstories.rdf | ja | 404 | 주석 처리 |
| WWD Japan | www.wwdjapan.com/feed | ja | 403 | 주석 처리 (로그인 벽) |
| Fashionsnap | www.fashionsnap.com/feed/ | ja | 404 | 주석 처리 |
| Jing Daily | jingdaily.com/feed/ | zh | 404 | 주석 처리 |
| Modaes (구 URL) | www.modaes.com/feed.xml | es | 404 | 주석 처리 — 신 URL로 대체 |
| Food Retail | www.foodretail.es/rss/portada | es | 404 | 주석 처리 |
| Marketing News ES | www.marketingnews.es/rss | es | 410 | 주석 처리 (영구 삭제) |

---

## C. 신규 추가 대상

### C-1. 검증된 트레이드 매체 (12개)

모두 `status=confirmed` (실시간 HTTP 200 + 유효 RSS + ≥10 items 확인 완료).

#### 한국어 (3개 추가)

| 이름 | URL | 카테고리 | items |
|---|---|---|---|
| 식품외식경제 | www.foodbank.co.kr/rss/allArticle.xml | 식음료 | 50 |
| 뷰티경제 | www.thebk.co.kr/rss/allArticle.xml | 뷰티 | 50 |
| 장업신문 | www.jangup.com/rss/allArticle.xml | 뷰티 | 50 |

#### 영어 (7개 추가)

| 이름 | URL | 카테고리 | items | 출처국 |
|---|---|---|---|---|
| WWD | wwd.com/feed/ | 패션 | 10 | USA |
| Glossy | www.glossy.co/feed/ | 뷰티 | 20 | USA |
| Modern Retail | www.modernretail.co/feed/ | 소비트렌드 | 10 | USA |
| Grocery Dive | www.grocerydive.com/feeds/news/ | 식음료 | 10 | USA |
| Restaurant Dive | www.restaurantdive.com/feeds/news/ | 식음료 | 10 | USA |
| Cosmetics Business | www.cosmeticsbusiness.com/rss | 뷰티 | 20 | GBR |
| Dezeen | www.dezeen.com/feed/ | 라이프스타일 | 50 | GBR |

#### 스페인어 (2개 추가)

| 이름 | URL | 카테고리 | items |
|---|---|---|---|
| Modaes.es (신 URL) | www.modaes.es/rss.xml | 패션 | 20 |
| Expansion Distribucion | e00-expansion.uecdn.es/rss/empresas/distribucion.xml | 소비트렌드 | 50 |

#### 일본어: 트레이드 RSS 전멸 (모두 403/404) → Google News JA로 전량 대체 (C-2)

#### 중국어: 기존 2개(36Kr, PANDAILY) 유지, 추가 트레이드 전멸 → Google News ZH로 보강 (C-2)

### C-2. Google News 키워드 기반 피드 (59개)

모두 검증 완료 (100% pass rate — Google News RSS는 매우 안정적).

**원칙**: 각 카테고리별로 언어별 2-4개 핵심 키워드 조합. 같은 주제를 여러 언어에서 커버하면 Call A 클러스터링이 cross-lingual merge로 중복 제거.

#### 한국어 (24개)

| 카테고리 | 키워드 4개 |
|---|---|
| 식음료 | `건강기능식품 OR 건기식` · `외식업 OR 프랜차이즈` · `편의점 OR 대형마트` · `대체육 OR 비건` |
| 뷰티 | `K뷰티 OR K-beauty` · `화장품 신제품` · `올리브영` · `인디 뷰티` |
| 패션 | `럭셔리 OR 명품` · `K패션` · `스트리트패션 OR 스트릿` · `리세일 OR 중고명품` |
| 라이프스타일 | `프리미엄 가전` · `호캉스 OR 호텔` · `인테리어 트렌드` · `웰니스` |
| 소비트렌드 | `MZ세대 소비` · `구독경제` · `DTC` · `가치소비` |
| 매크로트렌드 | `ESG 소비재` · `AI 리테일` · `금리 소비` · `인구 구조 소비` |

#### 일본어 (10개, 2개/카테고리)

| 카테고리 | 키워드 2개 |
|---|---|
| 식음료 | `食品 トレンド` · `外食 チェーン` |
| 뷰티 | `化粧品 ブランド` · `コスメ 新商品` |
| 패션 | `ファッション 業界` · `ラグジュアリー 日本` |
| 라이프스타일 | `ホテル ニュース` · `ライフスタイル ブランド` |
| 소비트렌드 | `Z世代 消費` · `サブスク 消費` |

#### 중국어 간체 (10개, 2개/카테고리)

| 카테고리 | 키워드 2개 |
|---|---|
| 식음료 | `食品 消费` · `餐饮 品牌` |
| 뷰티 | `化妆品 品牌` · `美妆 新品` |
| 패션 | `时尚 品牌` · `奢侈品` |
| 라이프스타일 | `生活方式 品牌` · `酒店 旅游` |
| 소비트렌드 | `Z世代 消费` · `国潮` |

#### 스페인어 (10개, 2개/카테고리)

| 카테고리 | 키워드 2개 |
|---|---|
| 식음료 | `alimentación tendencias` · `restaurante España` |
| 뷰티 | `belleza cosmética` · `skincare España` |
| 패션 | `moda España` · `lujo España` |
| 라이프스타일 | `estilo de vida marca` · `hotel viajes España` |
| 소비트렌드 | `consumo generación Z` · `DTC España` |

#### 영어 (5개, 소비/매크로만)

| 카테고리 | 키워드 |
|---|---|
| 소비트렌드 | `gen z consumer trends` · `subscription economy` |
| 매크로트렌드 | `consumer sentiment index` · `retail AI adoption` · `ESG consumer goods` |

---

## D. 개편 후 기대 커버리지

### D-1. 카테고리별 피드 수 (목표 5개 이상)

| 카테고리 | 현재 | 제안 후 | 목표 달성 |
|---|---|---|---|
| 식음료 | 2 | 15 | ✅ 초과달성 |
| 뷰티 | 1 | 14 | ✅ 초과달성 |
| 패션 | 2 | 13 | ✅ 초과달성 |
| 라이프스타일 | 3 | 13 | ✅ 초과달성 |
| 소비트렌드 | 3 | 16 | ✅ 초과달성 |
| 매크로트렌드 | 0 (키워드만) | 7 (전용) | ✅ 신규 커버 |

### D-2. 언어별 피드 수

| 언어 | 현재 | 제안 후 |
|---|---|---|
| 한국어 (ko) | 5 | 32 |
| 영어 (en) | 4 | 11 |
| 일본어 (ja) | 0 | 10 |
| 중국어 (zh) | 2 | 12 |
| 스페인어 (es) | 0 | 12 |
| **총합** | **11** | **77** |

### D-3. 하루 목표 기사 수 추정

- 트레이드 매체 14개 × 평균 5-10 new/day = 70-140 new/day
- Google News 59개 × 평균 10-30 new/day = 600-1,770 new/day (큰 중복 예상)
- Call A 클러스터링 후 예상 unique stories: 150-300/day
- max_per_cat=15 × 6 cats = 90 KeyIssues 선정 ← **원 목표 달성**

---

## E. 잠재 리스크 및 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| 피드 77개 → collector fetch 시간 증가 | 런타임 p95 < 10min 초과 우려 | 이미 병렬 fetch (workers=8), timeout 15s → 피드당 최대 2초 평균 예상, 총 ~150초 fetch. 플랜 범위 내 |
| Google News 중복 기사 폭증 | Call A 입력 비대화, 토큰 비용 증가 | 기존 precluster(rapidfuzz)에서 1차 제거, Call A가 2차 merge. 비용 가드 `MB_MAX_COST_USD` 유지 |
| 잘못된 카테고리 분류 | 탭 불일치 | 기존 `category_confirmed` LLM 스텝 + `legacy_aliases` 유지 |
| 모든 피드의 `status` 필드 처리 | uncertain 피드 재시도 정책 | 12개 신규 트레이드는 `confirmed`, Google News 59개도 `confirmed` (Google News RSS 안정성 검증됨) |

---

## F. 적용 순서 (승인 시)

1. `config/sources.yml` 백업 (git history로 충분)
2. 죽은 11개 피드 주석 처리 + 사유 주석 추가
3. 신규 12개 트레이드 추가 (`status: confirmed`)
4. 신규 59개 Google News 키워드 추가 (`source_type: CuratedSearch` — 신규 소스 타입)
5. (선택) `collector.py`에 `CuratedSearch` 타입 기본 정책 확인
6. 로컬 `pytest -q` 실행, 통과 확인
7. 로컬 dry-run 1회 실행, 피드 fetch 성공 · 카테고리 분포 확인
8. 커밋 + push
9. GitHub Actions 다음 07:00 KST 자동 실행 대기 (또는 수동 트리거)

---

## G. 사용자 질문

아래 5가지를 확정해주세요 (일괄 답변 가능):

1. **제거 11개 피드**: 주석 처리로 보존할까요, 완전 삭제할까요?
2. **패션비즈 / 어패럴뉴스**: RSS 엔드포인트 없음 확인. (A) Google News 키워드로 커버 / (B) 사용자께서 내부에서 RSS URL 확인해서 알려주실지
3. **Google News 키워드 세트**: 제안한 키워드 그대로 / 추가·변경 희망
4. **새 `source_type: CuratedSearch`** 도입 vs 기존 `TraditionalMedia` 재사용 (collector 변경 최소화면 후자)
5. **전체 승인**: 승인하시면 즉시 패치 작성 → 테스트 → 커밋 → push 진행
