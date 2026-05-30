# 칭호(Badge) DB 명세서

> **위치:** 추천 DB 명세 [`SPEC.md`](./SPEC.md)와 별개의 칭호 전용 테이블 명세.
> **구현 기준:** SQLite (`db/recommend.db`) — 추천 DB와 동일 파일에 칭호 테이블을 추가한다.
> 표기 규약(타입·제약·인덱스·트리거)은 [SPEC.md](./SPEC.md)의 *SQLite 표기 규약*을 그대로 따른다.
> **행동/판정 로직은 본 문서가 아니라 별도 명세** [`BADGE_LOGIC.md`](./BADGE_LOGIC.md)에서 다룬다.

## 개요

칭호 시스템은 두 테이블로 구성된다.

- **Badge** — 칭호 정의(메타데이터). 운영자가 시드로 채우는 정적 테이블.
- **UserBadge** — 유저별 칭호 획득 여부.

> **범위:** 본 명세는 칭호 데이터를 보관할 **최소 스키마**(정의 + 획득 여부)만 정의한다.
> 진행률(progress) 표시·획득 조건 판정 등 상세 구현은 추후 과제로 미룬다.

칭호 **획득 조건 판정에 쓰는 행동 신호는 별도로 저장하지 않고** 추천 DB([SPEC.md](./SPEC.md))의
`UserInteractionLog` / `UserFoodTagWeight` 를 재사용한다 (단일 진실 공급원). 따라서 본 명세에는
행동 로그 테이블이 없다.

## ① 칭호 정의 테이블

### Badge (칭호 정의 테이블)

- _설명:_ 칭호 1종 = 1행. 표시용 메타데이터(이름/아이콘/설명)와 분류만 보관.
- _참고:_ 조건 판정 로직(check)은 DB에 넣지 않고 애플리케이션/배치 코드가 보유한다.
  DB는 정의와 획득 상태만 저장한다.

| **컬럼명** | **데이터 타입** | **제약 조건** | **설명** |
| --- | --- | --- | --- |
| badge_id | TEXT | PK | 칭호 코드 (예: `spicy`, `ramen`) |
| category | TEXT | NOT NULL, CHECK(IN 'A','B','C','D','E') | 분류 (A 맛속성 / B 장르 / C 음식 / D 행동 / E 메타) |
| name | TEXT | NOT NULL | 표시명 (예: 칼칼함 마니아) |
| icon | TEXT | | 이모지 아이콘 |
| description | TEXT | NOT NULL | 획득 조건 설명 (UI 노출용) |

- `badge_id`는 자동 증가 정수가 아니라 **의미 있는 문자열 코드**(프론트 `badges.js`의 `id`와 동일)를
  PK로 쓴다. 프론트/배치 코드가 같은 식별자를 공유하기 위함.

## ② 유저 칭호 획득 테이블

### UserBadge (유저-칭호 획득 테이블)

- _설명:_ 유저가 (한 번이라도) 획득한 칭호를 `(user, badge)` 단위로 기록.
- _의미:_ 마이페이지 도감(보유/지난칭호) 렌더링의 단일 조회 대상.
- _갱신 방식:_ 칭호 재계산 시 `(user, badge)` 조합으로 UPSERT. 처음 획득하는
  시점(`earned_at` 이 NULL → 값)에만 `earned_at` 을 기록하고, **이후 절대 비우지 않는다.**

획득 "이력"과 현재 "유효 여부"를 분리해, 조건 미달로 비활성화돼도 이력이 남도록 한다.
추가로 활성↔비활성을 여러 번 오가도 **총 보유 기간**을 누적해 보관한다.

- **획득 이력** — `earned_at` (NULL이면 한 번도 획득 안 함). 한번 기록되면 영구 보존.
- **현재 유효 여부** — `is_active`. 재계산 시 조건 충족이면 1, 미달이면 0으로 토글.
- **총 보유 기간** — `held_total_days`(과거 활성 구간 합) + `active_since`(현재 활성 구간 시작).

| **컬럼명** | **데이터 타입** | **제약 조건** | **설명** |
| --- | --- | --- | --- |
| user_id | INTEGER | PK, FK (User) | 유저 ID |
| badge_id | TEXT | PK, FK (Badge) | 칭호 ID |
| is_active | INTEGER | NOT NULL, DEFAULT 0 | 현재 유효(조건 충족) 여부 (0/1). 조건 미달 시 0으로 비활성 |
| earned_at | TEXT | | 최초 획득 시각. 한번 기록 후 비우지 않음(이력) |
| active_since | TEXT | | 현재 활성 구간 시작 시각. 비활성이면 NULL |
| held_total_days | INTEGER | NOT NULL, DEFAULT 0 | 과거(종료된) 활성 구간들의 보유 기간 누적(일) |
| updated_at | TEXT | DEFAULT CURRENT_TIMESTAMP | 마지막 갱신 시각 |

- _상태 해석:_
  - **보유 중(활성)** = `is_active=1` (당연히 `earned_at IS NOT NULL`)
  - **지난 칭호(비활성)** = `is_active=0 AND earned_at IS NOT NULL` (땄었으나 현재 조건 미달 — 기록 보존)
  - **미획득** = `earned_at IS NULL` (행이 없거나 한 번도 못 땄음)

- _보유 기간 누적 규칙 (재계산 시):_
  - **비활성→활성 (0→1):** `active_since = CURRENT_TIMESTAMP`. (`earned_at` 이 NULL이면 같이 기록)
  - **활성→비활성 (1→0):** `held_total_days += (오늘 - active_since 의 일수)`, `active_since = NULL`.
  - **활성 유지(1→1)·비활성 유지(0→0):** `active_since`/`held_total_days` 변경 없음.
- _총 보유 기간 조회:_ `held_total_days + (is_active=1 이면 오늘 - active_since 일수, 아니면 0)`.
  즉 종료된 구간 누적(일) + 현재 진행 중인 구간(일). (현재 활성 구간은 조회 시점에 더해 계산)

- 복합 PK `(user_id, badge_id)` — 같은 조합은 항상 1행으로 유지하고 UPSERT.
- _FK 동작:_ `user_id`(→ User), `badge_id`(→ Badge) 모두 `ON DELETE CASCADE`.
  단, **칭호 비활성화는 `Badge`/`UserBadge` 행 삭제가 아니라 `is_active` 플래그로 처리**한다.
  행을 지우면 CASCADE로 획득 이력(`earned_at`)까지 사라지므로, 이력 보존을 위해 소프트 비활성화만 사용한다.
  (칭호 종류 자체를 은퇴시킬 경우에도 `Badge` 행 삭제 대신 추후 `Badge.is_active` 플래그 도입을 권장.)
- _인덱스:_ `idx_userbadge_user (user_id)` — 마이페이지 도감(유저별 전체 칭호) 조회.
- **`updated_at` 자동 갱신:** SQLite는 `ON UPDATE CURRENT_TIMESTAMP`를 미지원하므로,
  트리거 `trg_userbadge_updated_at` (AFTER UPDATE)로 행 갱신 시 `updated_at`을
  `CURRENT_TIMESTAMP`로 자동 변경한다. ([SPEC.md](./SPEC.md)의 `UserFoodTagWeight`와 동일 패턴)

## 인덱스 / 트리거 요약

| 객체 | 종류 | 대상 | 목적 |
| --- | --- | --- | --- |
| `idx_userbadge_user` | INDEX | UserBadge(user_id) | 유저별 칭호 도감 조회 |
| `trg_userbadge_updated_at` | TRIGGER | UserBadge (AFTER UPDATE) | `updated_at` 자동 갱신 |

## DDL (참고)

```sql
-- 칭호 정의
CREATE TABLE IF NOT EXISTS Badge (
    badge_id     TEXT PRIMARY KEY,
    category     TEXT NOT NULL CHECK (category IN ('A', 'B', 'C', 'D', 'E')),
    name         TEXT NOT NULL,
    icon         TEXT,
    description  TEXT NOT NULL
);

-- 유저 칭호 획득 상태
CREATE TABLE IF NOT EXISTS UserBadge (
    user_id           INTEGER NOT NULL,
    badge_id          TEXT NOT NULL,
    is_active           INTEGER NOT NULL DEFAULT 0,  -- 현재 유효(조건 충족) 여부
    earned_at           TEXT,                        -- 최초 획득 시각(이력, 비우지 않음)
    active_since        TEXT,                        -- 현재 활성 구간 시작(비활성이면 NULL)
    held_total_days     INTEGER NOT NULL DEFAULT 0,  -- 종료된 활성 구간 보유기간 누적(일)
    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, badge_id),
    FOREIGN KEY (user_id)  REFERENCES User(user_id)   ON DELETE CASCADE,
    FOREIGN KEY (badge_id) REFERENCES Badge(badge_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_userbadge_user ON UserBadge(user_id);

CREATE TRIGGER IF NOT EXISTS trg_userbadge_updated_at
AFTER UPDATE ON UserBadge
FOR EACH ROW BEGIN
    UPDATE UserBadge
       SET updated_at = CURRENT_TIMESTAMP
     WHERE user_id  = NEW.user_id
       AND badge_id = NEW.badge_id;
END;
```

> 칭호 29종의 구체 목록·획득 조건·판정 흐름은 [`BADGE_LOGIC.md`](./BADGE_LOGIC.md) 참조.
