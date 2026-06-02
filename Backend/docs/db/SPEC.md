# DB 명세서

> **구현 기준:** SQLite (`db/recommend.db`). 초기화 코드는 [`src/data/database/schema.py`](../../src/data/database/schema.py).
> 본 명세는 SQLite 실제 구현과 1:1로 일치하도록 작성한다.

## SQLite 표기 규약

| 표기 | 의미 |
| --- | --- |
| `INTEGER PK AUTOINCREMENT` | 자동 증가 정수 기본키 |
| `TEXT` | 문자열 (SQLite는 길이 제한을 강제하지 않음. VARCHAR(n) 대신 TEXT 사용) |
| `TEXT CHECK(...)` | ENUM 대체. 허용값을 CHECK 제약으로 제한 |
| `TEXT DEFAULT CURRENT_TIMESTAMP` | 행 생성 시각 자동 기록 |
| `ON UPDATE` | SQLite는 미지원 → **트리거**로 구현 (해당 테이블에 명시) |

> SQLite는 FK를 선언해도 자식 컬럼에 인덱스를 자동 생성하지 않는다. 따라서 조인·역참조에 쓰이는 FK 컬럼에는 **수동 인덱스**를 추가하며, 각 테이블 하단에 명시한다.
> FK 제약을 적용하려면 연결마다 `PRAGMA foreign_keys = ON` 이 필요하다 (`connect()`에서 설정).

## ① 마스터 테이블 (기준 정보)

크롤링된 제각각의 메뉴명을 표준 음식명과 매핑하고, 고정된 14개의 태그를 관리하는 테이블입니다.

### User (유저 테이블)

| **컬럼명** | **데이터 타입**          | **제약 조건** | **설명**   |
| ------- | ------------------- | --------- | -------- |
| user_id | INTEGER AUTOINCREMENT | PK        | 유저 고유 ID |
| email   | TEXT                | UNIQUE    | 유저 계정    |

### Food (표준 음식 테이블)

| **컬럼명**   | **데이터 타입**          | **제약 조건** | **설명**           |
| --------- | ------------------- | --------- | ---------------- |
| food_id   | INTEGER AUTOINCREMENT | PK        | 표준 음식 고유 ID      |
| food_name | TEXT                | NOT NULL  | 표준 음식명 (예: 김치찌개) |

### CrawledMenu (크롤링 메뉴 매핑 테이블)

| **컬럼명**         | **데이터 타입**          | **제약 조건** | **설명**                    |
| --------------- | ------------------- | --------- | ------------------------- |
| menu_id         | INTEGER AUTOINCREMENT | PK        | 크롤링 메뉴 고유 ID              |
| restaurant_name | TEXT                | NOT NULL  | 실제 음식점 이름                 |
| menu_name       | TEXT                | NOT NULL  | 크롤링된 메뉴명. details.db에서 참조 |
| food_id         | INTEGER             | FK (Food) | 매핑될 표준 음식 ID              |

- _인덱스:_ `idx_crawledmenu_food (food_id)` — 특정 표준 음식을 파는 실메뉴/음식점 역추적.
- _참고:_ `menu_name`은 별도 DB(`details.db`)의 메뉴명을 논리적으로 참조한다. SQLite는 DB 간 FK를 걸 수 없으므로 값으로만 연결한다(FK 미강제).

### Tag (고정 태그 테이블)

| **컬럼명**  | **데이터 타입**          | **제약 조건**       | **설명**                    |
| -------- | ------------------- | --------------- | ------------------------- |
| tag_id   | INTEGER AUTOINCREMENT | PK              | 태그 고유 ID                  |
| tag_name | TEXT                | NOT NULL, UNIQUE | 태그명 (국물있는, 얼큰한, 야식 등 14개) |

## ② 매핑 및 관계 테이블

음식이 기본적으로 어떤 태그 성향을 가졌는지 정의하는 정적 관계 테이블입니다.

### FoodTag (음식-태그 매핑 테이블)

- _설명:_ 특정 음식(김치찌개)이 기본적으로 가지는 태그(국물있는, 얼큰한)를 다대다(M:N)로 연결합니다.
- _CF 활용:_ 이 테이블을 기반으로 '아이템-태그' 프로필 행렬을 쉽게 구축할 수 있습니다.

| **컬럼명** | **데이터 타입** | **제약 조건**     | **설명**   |
| ------- | ---------- | ------------- | -------- |
| food_id | INTEGER    | PK, FK (Food) | 표준 음식 ID |
| tag_id  | INTEGER    | PK, FK (Tag)  | 태그 ID    |

- _인덱스:_ `idx_foodtag_tag (tag_id)` — 특정 태그를 가진 음식 목록 조회 (역방향).
- _FK 동작:_ `food_id`, `tag_id` 모두 `ON DELETE CASCADE`.

## ③ 유저 행동 및 추천 데이터 테이블 (동적 데이터)

추천 세션을 부모로 두고, 자식 로그 테이블 2개(태그 선택 / 음식 행동)에 원천 이벤트를 기록합니다. 추천 알고리즘이 빠르게 조회할 수 있도록 **유저-음식별 태그 가중치**를 별도의 집계 테이블로 관리합니다.

### RecommendationSession (추천 세션 테이블)

- _설명:_ 추천 요청 1건 = 1행. 이 세션 내에서 발생한 태그 선택과 음식 행동을 묶는 부모 키 역할.
- _관계:_ `UserTagSelection`, `UserInteractionLog`가 `session_id`를 FK로 참조.

| **컬럼명**     | **데이터 타입**          | **제약 조건**                  | **설명**         |
| ----------- | ------------------- | -------------------------- | -------------- |
| session_id  | INTEGER AUTOINCREMENT | PK                         | 추천 세션 고유 ID    |
| user_id     | INTEGER             | FK (User)                  | 추천을 요청한 유저 ID  |
| created_at  | TEXT                | DEFAULT CURRENT_TIMESTAMP  | 추천 요청 시각       |

- _인덱스:_ `idx_recsession_user (user_id)` — 유저별 추천 세션 조회.

### UserTagSelection (유저 태그 선택 로그)

- _설명:_ 추천 요청 시 유저가 선택한 태그를 1태그당 1행으로 기록 (세션당 N행).
- _용도:_ 유저의 명시적 태그 선호 시그널 및 `UserFoodTagWeight` 집계의 입력.

| **컬럼명**       | **데이터 타입**          | **제약 조건**                     | **설명**         |
| ------------- | ------------------- | ----------------------------- | -------------- |
| selection_id  | INTEGER AUTOINCREMENT | PK                            | 태그 선택 로그 ID    |
| session_id    | INTEGER             | FK (RecommendationSession)    | 소속 추천 세션 ID    |
| tag_id        | INTEGER             | FK (Tag)                      | 유저가 선택한 태그 ID  |

- _인덱스:_ `idx_tagsel_session (session_id)` — 세션에 속한 태그 선택 조회.
- _FK 동작:_ `session_id`는 `ON DELETE CASCADE` (세션 삭제 시 선택 로그도 삭제).

### UserInteractionLog (유저 음식 행동 로그)

- _설명:_ 클릭/최종선택 같은 음식 행동을 발생 시점마다 1행씩 기록 (세션당 N행).
- _작동 방식:_ 가중치 값(1, 2)은 컬럼에 박지 않고 `action_type` 으로 의미만 보존합니다. 합산 시 쿼리에서 `CASE WHEN action_type = 'click' THEN 1 WHEN 'final_select' THEN 2 END`로 매핑하여 SUM합니다. → 가중치 정책이 바뀌어도 로그를 건드릴 필요 없음.

| **컬럼명**      | **데이터 타입**                              | **제약 조건**                     | **설명**            |
| ------------ | --------------------------------------- | ----------------------------- | ----------------- |
| log_id       | INTEGER AUTOINCREMENT                     | PK                            | 행동 로그 ID          |
| session_id   | INTEGER                                 | FK (RecommendationSession)    | 소속 추천 세션 ID       |
| food_id      | INTEGER                                 | FK (Food)                     | 대상 음식 ID          |
| action_type  | TEXT CHECK(IN 'click','final_select')   | NOT NULL                      | 행동 유형 (클릭/최종선택)   |
| created_at   | TEXT                                    | DEFAULT CURRENT_TIMESTAMP     | 발생 시각             |

- _인덱스:_ `idx_interaction_session (session_id)` — 세션에 속한 행동 로그 조회.
- _FK 동작:_ `session_id`는 `ON DELETE CASCADE`.

### UserFoodTagWeight (유저-음식별 태그 가중치 집계 테이블) -- 가중치 문제 생길 위험 발생.

- _설명:_ 같은 세션의 태그 선택 × 음식 행동을 결합한 시그널을 **(유저, 음식, 태그)** 단위로 사전 집계.
- _의미:_ "유저가 이 음식을 어떤 태그 의도로 골랐는지"를 누적. 추천 시 단일 테이블 조회로 빠르게 활용.
- _갱신 방식:_ 클릭/최종선택 발생 시 → 해당 세션의 `UserTagSelection`을 조회하여 `(user, food, tag)` 각 조합마다 `total_weight += (액션 가중치)` UPSERT.
  - 예: 세션 100에서 `[얼큰한, 국물있는]` 선택 후 김치찌개 최종선택(+2) → `(user, 김치찌개, 얼큰한)`, `(user, 김치찌개, 국물있는)` 두 행에 각각 `+2`.

| **컬럼명**       | **데이터 타입** | **제약 조건**         | **설명**                |
| ------------- | ---------- | ----------------- | --------------------- |
| user_id       | INTEGER    | PK, FK (User)     | 유저 ID                 |
| food_id       | INTEGER    | PK, FK (Food)     | 음식 ID                 |
| tag_id        | INTEGER    | PK, FK (Tag)      | 태그 ID                 |
| total_weight  | INTEGER    | NOT NULL, DEFAULT 0 | 누적 가중치 (클릭=+1, 최종=+2) |
| updated_at    | TEXT       | DEFAULT CURRENT_TIMESTAMP | 마지막 갱신 시각  |

> 복합 PK `(user_id, food_id, tag_id)` — 같은 조합은 항상 1행으로 유지하고 UPSERT.
> _FK 동작:_ `user_id`, `food_id`, `tag_id` 모두 `ON DELETE CASCADE`.
> **`updated_at` 자동 갱신:** SQLite는 `ON UPDATE CURRENT_TIMESTAMP`를 지원하지 않으므로, 트리거 `trg_userfoodtagweight_updated_at` (AFTER UPDATE)로 행 갱신 시 `updated_at`을 `CURRENT_TIMESTAMP`로 자동 변경한다.

## 인덱스 / 트리거 요약

| 객체 | 종류 | 대상 | 목적 |
| --- | --- | --- | --- |
| `idx_crawledmenu_food` | INDEX | CrawledMenu(food_id) | 음식→실메뉴 역추적 |
| `idx_foodtag_tag` | INDEX | FoodTag(tag_id) | 태그→음식 역방향 조회 |
| `idx_recsession_user` | INDEX | RecommendationSession(user_id) | 유저별 세션 조회 |
| `idx_tagsel_session` | INDEX | UserTagSelection(session_id) | 세션별 태그 선택 조회 |
| `idx_interaction_session` | INDEX | UserInteractionLog(session_id) | 세션별 행동 로그 조회 |
| `trg_userfoodtagweight_updated_at` | TRIGGER | UserFoodTagWeight (AFTER UPDATE) | `updated_at` 자동 갱신 |

> `User.email`, `Tag.tag_name`의 UNIQUE 제약은 SQLite가 자동 인덱스를 생성하므로 위 목록에 별도로 두지 않는다.
