# DB 명세서

## ① 마스터 테이블 (기준 정보)

크롤링된 제각각의 메뉴명을 표준 음식명과 매핑하고, 고정된 14개의 태그를 관리하는 테이블입니다.

### User (유저 테이블)

| **컬럼명** | **데이터 타입**   | **제약 조건** | **설명**   |
| ------- | ------------ | --------- | -------- |
| user_id | INT (AI)     | PK        | 유저 고유 ID |
| email   | VARCHAR(100) | UNIQUE    | 유저 계정    |

### Food (표준 음식 테이블)

| **컬럼명**   | **데이터 타입**  | **제약 조건** | **설명**           |
| --------- | ----------- | --------- | ---------------- |
| food_id   | INT (AI)    | PK        | 표준 음식 고유 ID      |
| food_name | VARCHAR(50) | NOT NULL  | 표준 음식명 (예: 김치찌개) |

### CrawledMenu (크롤링 메뉴 매핑 테이블)

| **컬럼명**         | **데이터 타입**   | **제약 조건** | **설명**                    |
| --------------- | ------------ | --------- | ------------------------- |
| menu_id         | INT (AI)     | PK        | 크롤링 메뉴 고유 ID              |
| restaurant_name | VARCHAR(100) | NOT NULL  | 실제 음식점 이름                 |
| menu_name       | VARCHAR(100) | NOT NULL  | 크롤링된 메뉴명. details.db에서 참조 |
| food_id         | INT          | FK (Food) | 매핑될 표준 음식 ID              |

### Tag (고정 태그 테이블)

| **컬럼명**  | **데이터 타입**  | **제약 조건** | **설명**                    |
| -------- | ----------- | --------- | ------------------------- |
| tag_id   | INT (AI)    | PK                | 태그 고유 ID                  |
| tag_name | VARCHAR(20) | NOT NULL, UNIQUE  | 태그명 (국물있는, 얼큰한, 야식 등 14개) |

## ② 매핑 및 관계 테이블

음식이 기본적으로 어떤 태그 성향을 가졌는지 정의하는 정적 관계 테이블입니다.

### FoodTag (음식-태그 매핑 테이블)

- _설명:_ 특정 음식(김치찌개)이 기본적으로 가지는 태그(국물있는, 얼큰한)를 다대다(M:N)로 연결합니다.
- _CF 활용:_ 이 테이블을 기반으로 '아이템-태그' 프로필 행렬을 쉽게 구축할 수 있습니다.

| **컬럼명** | **데이터 타입** | **제약 조건**     | **설명**   |
| ------- | ---------- | ------------- | -------- |
| food_id | INT        | PK, FK (Food) | 표준 음식 ID |
| tag_id  | INT        | PK, FK (Tag)  | 태그 ID    |

## ③ 유저 행동 및 추천 데이터 테이블 (동적 데이터)

추천 세션을 부모로 두고, 자식 로그 테이블 2개(태그 선택 / 음식 행동)에 원천 이벤트를 기록합니다. 추천 알고리즘이 빠르게 조회할 수 있도록 **유저-음식별 태그 가중치**를 별도의 집계 테이블로 관리합니다.

### RecommendationSession (추천 세션 테이블)

- _설명:_ 추천 요청 1건 = 1행. 이 세션 내에서 발생한 태그 선택과 음식 행동을 묶는 부모 키 역할.
- _관계:_ `UserTagSelection`, `UserInteractionLog`가 `session_id`를 FK로 참조.

| **컬럼명**     | **데이터 타입** | **제약 조건** | **설명**         |
| ----------- | ---------- | --------- | -------------- |
| session_id  | INT (AI)   | PK        | 추천 세션 고유 ID    |
| user_id     | INT        | FK (User) | 추천을 요청한 유저 ID  |
| created_at  | TIMESTAMP  | DEFAULT CURRENT_TIMESTAMP | 추천 요청 시각 |

### UserTagSelection (유저 태그 선택 로그)

- _설명:_ 추천 요청 시 유저가 선택한 태그를 1태그당 1행으로 기록 (세션당 N행).
- _용도:_ 유저의 명시적 태그 선호 시그널 및 `UserFoodTagWeight` 집계의 입력.

| **컬럼명**       | **데이터 타입** | **제약 조건**                     | **설명**         |
| ------------- | ---------- | ----------------------------- | -------------- |
| selection_id  | INT (AI)   | PK                            | 태그 선택 로그 ID    |
| session_id    | INT        | FK (RecommendationSession)    | 소속 추천 세션 ID    |
| tag_id        | INT        | FK (Tag)                      | 유저가 선택한 태그 ID  |

### UserInteractionLog (유저 음식 행동 로그)

- _설명:_ 클릭/최종선택 같은 음식 행동을 발생 시점마다 1행씩 기록 (세션당 N행).
- _작동 방식:_ 가중치 값(1, 2)은 컬럼에 박지 않고 `action_type` ENUM으로 의미만 보존합니다. 합산 시 쿼리에서 `CASE WHEN action_type = 'click' THEN 1 WHEN 'final_select' THEN 2 END`로 매핑하여 SUM합니다. → 가중치 정책이 바뀌어도 로그를 건드릴 필요 없음.

| **컬럼명**      | **데이터 타입**                       | **제약 조건**                     | **설명**            |
| ------------ | -------------------------------- | ----------------------------- | ----------------- |
| log_id       | INT (AI)                         | PK                            | 행동 로그 ID          |
| session_id   | INT                              | FK (RecommendationSession)    | 소속 추천 세션 ID       |
| food_id      | INT                              | FK (Food)                     | 대상 음식 ID          |
| action_type  | ENUM('click', 'final_select')    | NOT NULL                      | 행동 유형 (클릭/최종선택)   |
| created_at   | TIMESTAMP                        | DEFAULT CURRENT_TIMESTAMP     | 발생 시각             |

### UserFoodTagWeight (유저-음식별 태그 가중치 집계 테이블)

- _설명:_ 같은 세션의 태그 선택 × 음식 행동을 결합한 시그널을 **(유저, 음식, 태그)** 단위로 사전 집계.
- _의미:_ "유저가 이 음식을 어떤 태그 의도로 골랐는지"를 누적. 추천 시 단일 테이블 조회로 빠르게 활용.
- _갱신 방식:_ 클릭/최종선택 발생 시 → 해당 세션의 `UserTagSelection`을 조회하여 `(user, food, tag)` 각 조합마다 `total_weight += (액션 가중치)` UPSERT.
  - 예: 세션 100에서 `[얼큰한, 국물있는]` 선택 후 김치찌개 최종선택(+2) → `(user, 김치찌개, 얼큰한)`, `(user, 김치찌개, 국물있는)` 두 행에 각각 `+2`.

| **컬럼명**       | **데이터 타입** | **제약 조건**         | **설명**                |
| ------------- | ---------- | ----------------- | --------------------- |
| user_id       | INT        | PK, FK (User)     | 유저 ID                 |
| food_id       | INT        | PK, FK (Food)     | 음식 ID                 |
| tag_id        | INT        | PK, FK (Tag)      | 태그 ID                 |
| total_weight  | INT        | DEFAULT 0         | 누적 가중치 (클릭=+1, 최종=+2) |
| updated_at    | TIMESTAMP  | ON UPDATE CURRENT_TIMESTAMP | 마지막 갱신 시각  |

> 복합 PK `(user_id, food_id, tag_id)` — 같은 조합은 항상 1행으로 유지하고 UPSERT.
