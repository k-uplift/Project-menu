# 칭호(Badge) 판정 로직 명세서

> **위치:** 테이블 구조는 [`BADGE_SPEC.md`](./BADGE_SPEC.md), 추천 DB는 [`SPEC.md`](./SPEC.md).
> 본 문서는 "칭호 29종이 무엇이고, 어떤 행동을 어떻게 집계해 획득을 판정하는가"를 다룬다.
> **원천:** `origin/llm-tag` 브랜치의 프론트 구현 `Frontend/services/badges.js` + `behaviorTrackingService.js`
> (5/29 사용자 결정, 5 카테고리 29종)를 DB 브랜치 기준으로 옮긴 것.

## 0. 배경

`llm-tag` 브랜치는 칭호를 **프론트 전용**(AsyncStorage 로컬 누적, 즉석 재계산)으로 구현했고,
주석에 *"추후 백엔드 연결: POST /api/events로 교체, 로컬은 오프라인 큐로"* 라 명시했다.
DB 브랜치는 이 칭호를 영속화한다 — 행동 로그는 recommend DB를 재사용하고, 판정 결과만
[`UserBadge`](./BADGE_SPEC.md#-유저-칭호-획득-테이블)에 저장한다.

## 1. 행동 신호 → 추천 DB 매핑

칭호 판정은 추천 DB([SPEC.md](./SPEC.md))의 로그를 입력으로 쓴다. 별도 행동 테이블은 두지 않는다.

| 프론트(llm-tag) | 추천 DB(SPEC.md) | 의미 | 점수 |
| --- | --- | --- | --- |
| `food_card_click` | `UserInteractionLog.action_type='click'` | 관심(클릭) | +1 |
| `navigate_click` | `UserInteractionLog.action_type='final_select'` | 최종선택(길찾기) | +2 |
| `delivery_click` | `UserInteractionLog.action_type='final_select'` | 최종선택(배달) | +2 |
| `seedCounts[태그]` | `UserFoodTagWeight.total_weight` / `FoodTag` | 유저×음식×태그 누적 | — |

- **칭호 카운트는 (특별 표기 외) 최종선택(`final_select`) 횟수** 로 센다. 클릭은 E(눈팅러)에서만 사용.
- 점수(1/2)는 추천 가중치 개념이고, 칭호의 "횟수"와는 별개다.

> **채널 미구분 한계:** 프론트는 최종선택을 길찾기/배달로 나누지만 추천 DB의 `action_type`은
> `final_select` 하나뿐이다. 현재 칭호 조건엔 채널 구분이 필요 없어 문제 없으나, 추후 필요하면
> ENUM 확장 또는 `channel` 컬럼 추가가 필요하다. → §5.

## 2. 칭호 29종 정의

> 모든 조건은 별도 표기가 없으면 **최종선택 횟수** 기준.

### A. 맛 속성 — 8종 (시드 태그 기반)

| badge_id | 칭호 | 아이콘 | 조건 |
| --- | --- | --- | --- |
| spicy | 칼칼함 마니아 | 🌶 | `얼큰한` 5회+ |
| soup | 국물 애호가 | 🍲 | `국물있는` 5회+ (한식국물탕 보강) |
| hearty | 든든한 한 끼파 | 🍚 | `든든한` 5회+ |
| mild | 담백 미식가 | 🥗 | `담백한` 5회+ |
| hangover | 해장 전문가 | 🍻 | `해장` 3회+ (희소 시드라 임계 낮음) |
| rich | 진한 맛 추구자 | 🔥 | `진한` 5회+ |
| light | 가벼운 한 입파 | ☁️ | `가벼운` 5회+ |
| midnight | 야식러 | 🌙 | `야식` 태그를 **22~02시**에 3회+ |

### B. 장르(카테고리) — 6종

| badge_id | 칭호 | 아이콘 | 조건 |
| --- | --- | --- | --- |
| korean | 한식 마스터 | 🇰🇷 | 한식(국물탕/고기/면밥/조림찜 합산) 10회+ |
| japanese | 일식 애호가 | 🍣 | 일식 5회+ |
| chinese | 중식 탐험가 | 🥟 | 중식 5회+ |
| western | 양식 미식가 | 🍝 | 양식 5회+ |
| chicken | 치킨 헌터 | 🍗 | 치킨 3회+ |
| dessert | 디저트 러버 | 🍰 | 디저트 5회+ |

### C. 특정 음식(kind) — 6종

| badge_id | 칭호 | 아이콘 | 조건 |
| --- | --- | --- | --- |
| ramen | 라면 충신 | 🍜 | `라면` 3회+ |
| tteokbokki | 떡볶이 마니아 | 🌶 | `떡볶이` 3회+ |
| meat | 고기파 | 🥩 | 고기류 묶음 5회+ |
| sashimi | 회 마니아 | 🐟 | 회류 묶음 3회+ |
| noodle | 면 러버 | 🥢 | 면류 묶음 5회+ |
| rice | 밥심러 | 🍚 | 밥류 묶음 5회+ |

### D. 행동 패턴 — 6종

| badge_id | 칭호 | 아이콘 | 조건 |
| --- | --- | --- | --- |
| morning | 아침형 인간 | 🌅 | 6~10시 최종선택 5회+ |
| lunch | 점심 인사이더 | ☀️ | 11~14시 최종선택 10회+ |
| dawn | 새벽 사냥꾼 | 🌃 | 0~5시 **검색** 3회+ |
| explorer | 새로운 맛 탐험가 | 🧭 | 서로 다른 카테고리 5종+ 에서 최종선택 |
| regular | 단골 | ❤️ | 같은 식당 최종선택 3회+ |
| decisive | 결정파 | 🎯 | 검색 후 첫 카드 그대로 선택 70%+ (10회+ 검색 시) |

### E. 희귀·메타 — 3종

| badge_id | 칭호 | 아이콘 | 조건 |
| --- | --- | --- | --- |
| master | 만능 미식가 | 🌟 | 14개 시드 중 10종+ 에서 최종선택 1회+ |
| specialist | 한 우물 파 | 🎭 | 한 시드 태그가 최종선택의 60%+ 점유 (표본 10회+) |
| watcher | 눈팅러 | 👁 | 클릭 20회+ & 최종선택 5회 미만 (관심↔실행 갭) |

## 3. kind 묶음 정의 (C 칭호용)

meat/sashimi/noodle/rice는 단일 kind가 아니라 **묶음(set) 합산**으로 판정한다.
(프론트 `badges.js`의 `MEAT_KINDS` 등과 동일. DB 이식 시 판정 코드 상수 또는 매핑 테이블로 보관.)

- **MEAT_KINDS**: 삼겹살·오겹살·목살·갈비·등심·차돌박이·막창·곱창·대창·제육볶음·불고기·보쌈·족발·수육·갈비찜·닭갈비·찜닭·스테이크 …
- **SASHIMI_KINDS**: 스시·초밥·사시미·회·오마카세·니기리·마키·롤·회덮밥·참치회·광어회·연어회·사시미동
- **NOODLE_KINDS**: 라면·라멘·우동·소바·메밀·쌀국수·짜장면·짬뽕·칼국수·잔치국수·쫄면·막국수·냉면·국수·콩국수·파스타·스파게티·까르보나라·로제파스타 …
- **RICE_KINDS**: 비빔밥·볶음밥·김밥·덮밥·제육덮밥·오므라이스·돌솥비빔밥·주먹밥·카레·짜장밥·회덮밥·가츠동·규동·텐동·장어덮밥 …
- **KOREAN_CATEGORIES** (B 한식 마스터): 한식국물탕·한식고기·한식면밥·한식조림찜

> 전체 목록은 프론트 `badges.js` 단일 출처를 유지하고, 백엔드는 이를 동기화한다.

## 4. 판정 흐름

판정에 필요한 통계(`stats`)를 추천 DB 로그에서 집계한 뒤, 칭호별 조건을 평가하고
결과를 [`UserBadge`](./BADGE_SPEC.md#-유저-칭호-획득-테이블) 에 반영한다.

> **스키마 정합:** 출력은 BADGE_SPEC 의 컬럼만 쓴다. 즉 `is_active`(현재 조건 충족 여부),
> `earned_at`(최초 획득 이력), `active_since`/`held_total_days`(보유 기간 누적). 옛 설계의
> `earned`/`progress_current`/`progress_target` 컬럼은 더 이상 없다(진행률 표시는 추후 과제).

```
[실시간 — 추천 DB]
유저 행동 발생 → UserInteractionLog INSERT
                → UserFoodTagWeight UPSERT

[칭호 재계산]
  1. stats 집계 (유저 단위)
       - seedCounts[태그]        : 시드별 최종선택 수      (A·E)
       - categoryCounts[카테고리] : 카테고리별 최종선택 수   (B)  ※ 한식 4종 → '한식' 합산
       - kindCounts[kind]        : 음식종류별 최종선택 수   (C)
       - hourBuckets / midnight  : 시간대별 최종선택 수     (A야식·D)
       - dawnSearches            : 0~5시 검색 수           (D)
       - uniqueCategories/Seeds  : 다양성                  (D·E)
       - maxStoreCount           : 같은 식당 반복 수        (D 단골)
       - clickCount/finalCount   : 관심 vs 실행            (E 눈팅러)
       - totalSeedHits/topSeedShare : 시드 점유율          (E 한 우물)
  2. 각 칭호 조건 평가 → meets = (조건 충족 여부, bool)
  3. (user, badge) 마다 UserBadge UPSERT  ── 아래 상태 전이 규칙대로
```

### UserBadge 상태 전이 규칙

재계산 시 `meets`(이번 평가의 조건 충족 여부)와 직전 `is_active` 를 비교해 갱신한다.
보유 기간은 **일(day) 단위**로 누적한다(BADGE_SPEC 의 `held_total_days`).

| 직전 상태 | 이번 `meets` | 동작 |
| --- | --- | --- |
| 행 없음 / `earned_at IS NULL` | true | INSERT. `is_active=1`, `earned_at=now`, `active_since=now` (**최초 획득**) |
| `is_active=0` (지난 칭호) | true | **재획득.** `is_active=1`, `active_since=now`. `earned_at` 은 **유지**(덮어쓰지 않음) |
| `is_active=1` | true | 유지. 변경 없음(`active_since`/`held_total_days` 불변) |
| `is_active=1` | false | **비활성화.** `held_total_days += (now - active_since 의 일수)`, `active_since=NULL`, `is_active=0` |
| `is_active=0` | false | 유지. 변경 없음 |
| 행 없음 | false | INSERT 안 함(또는 `is_active=0, earned_at=NULL` 로만 둠) |

- `earned_at` 은 **한번 기록되면 절대 비우거나 덮어쓰지 않는다**(획득 이력의 단일 기준).
- 비활성화는 행 삭제가 아니라 `is_active=0` 토글로만 한다 → 지난 칭호 이력·보유 기간 보존.
- **총 보유 기간 조회:** `held_total_days + (is_active=1 이면 now - active_since 일수, 아니면 0)`.
- 일수 계산은 SQLite `julianday` 기준 예: `CAST(julianday('now') - julianday(active_since) AS INTEGER)`.

### 재계산 시점 (옵션)

| 방식 | 동작 | 비고 |
| --- | --- | --- |
| A. 실시간 | 행동 INSERT 직후 재계산 | 즉시 반영, 비용 ↑ |
| B. Lazy 배치 | 로그인/마이페이지 진입 시 재계산 | 단순·저비용, 반영 지연. **초기 권장** |
| C. 주기 배치 | 정기 배치로 일괄 재계산 | 대규모 시 |

- 칭호는 즉시성이 낮으므로 **B(마이페이지 진입 시 lazy 재계산)** 로 충분.

## 5. 데이터 의존성 / 미해결

칭호 일부는 추천 DB에 아직 없는 신호를 요구한다.

| 신호 | 필요 칭호 | 현재 출처 | 추천 DB 상태 |
| --- | --- | --- | --- |
| 음식점 카테고리 | B 전체 | `details.db` 카테고리 | 추천 DB에 없음 → join 필요 |
| 음식 종류(kind) | C 전체 | 프론트 `foodName` | `Food.food_name` 와 대응 |
| store_id | D 단골 | `details.db` store | 추천 DB는 `restaurant_name`(텍스트)만 |
| 검색 시각 | D 새벽 | 프론트 검색 로그 | `RecommendationSession.created_at` 프록시 |
| 검색→첫카드 선택 | D 결정파 | (없음) | **미구현 — 항상 false** |

### 결정 보류 항목

- **카테고리·store_id 정합성**: 칭호 B·D는 음식점 카테고리/store_id가 필요. 추천 DB의
  `CrawledMenu.restaurant_name`(텍스트)을 `details.db` store_id 기반으로 정규화할지 결정 필요.
- **final_select 채널 구분**: 길찾기/배달 분리가 칭호에 필요해지면 `action_type` ENUM 확장.
- **decisive(결정파)**: '검색→첫 카드 선택' 시그널 부재로 미구현. 검색-선택 연결 데이터 필요.
- **kind 묶음 위치**: DB 매핑 테이블 vs 판정 코드 상수 (현재 프론트 단일 출처).
- **재계산 방식·도입 시점**: A/B/C 중 택1, MVP 포함 여부.
