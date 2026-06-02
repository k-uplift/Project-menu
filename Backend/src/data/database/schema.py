"""recommend.db 스키마 초기화. 태그 기반 추천 엔진 전용 DB.

docs/db/SPEC.md 의 논리 테이블을 그대로 옮긴 것.
  ① 마스터  : User / Food / CrawledMenu / Tag
  ② 매핑    : FoodTag (음식 ↔ 태그 정적 매핑, M:N)
  ③ 동적    : RecommendationSession / UserTagSelection /
              UserInteractionLog / UserFoodTagWeight

SPEC(MySQL 표기) → SQLite 매핑 메모:
  - INT (AI) PK              → INTEGER PRIMARY KEY AUTOINCREMENT
  - VARCHAR(n)               → TEXT (SQLite 는 길이 제한을 강제하지 않음)
  - ENUM(...)                → TEXT + CHECK 제약
  - TIMESTAMP DEFAULT now    → TEXT DEFAULT CURRENT_TIMESTAMP
  - ON UPDATE CURRENT_TIMESTAMP → SQLite 미지원 → 트리거로 구현

크롤링 결과(details.db / stores·menus·business_hours)는 별도 DB 다.
CrawledMenu.menu_name 은 details.db 의 메뉴명을 논리적으로 참조하지만,
SQLite 는 DB 간 FK 를 걸 수 없어 값으로만 연결한다(FK 미강제).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = BACKEND_ROOT / "db" / "recommend.db"
DETAILS_DB_PATH = BACKEND_ROOT / "db" / "details.db"

SCHEMA = """
-- ── ① 마스터 테이블 (기준 정보) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS User (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT UNIQUE,                    -- 유저 계정(로그인 ID)
    password_hash  TEXT NOT NULL DEFAULT ''        -- 비밀번호 해시(평문 저장 금지)
);

-- 표준 음식명. 크롤링된 제각각의 메뉴명이 매핑되는 기준점
CREATE TABLE IF NOT EXISTS Food (
    food_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    food_name  TEXT NOT NULL                      -- 표준 음식명 (예: 김치찌개)
);

-- 크롤링 실메뉴 → 표준 음식 매핑. menu_name 은 details.db 값을 논리 참조
CREATE TABLE IF NOT EXISTS CrawledMenu (
    menu_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_name  TEXT NOT NULL,               -- 실제 음식점 이름
    menu_name        TEXT NOT NULL,               -- 크롤링된 메뉴명 (details.db 참조)
    food_id          INTEGER,                     -- 매핑될 표준 음식 ID
    FOREIGN KEY (food_id) REFERENCES Food(food_id)
);
-- 역추적용: 특정 표준 음식을 파는 실메뉴/음식점 조회
CREATE INDEX IF NOT EXISTS idx_crawledmenu_food ON CrawledMenu(food_id);

-- 고정 14개 태그 (국물있는, 얼큰한, 야식 등)
CREATE TABLE IF NOT EXISTS Tag (
    tag_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name  TEXT NOT NULL UNIQUE                -- 태그명
);

-- ── ② 매핑 및 관계 테이블 (정적) ─────────────────────────────────
-- 음식이 기본적으로 가지는 태그 성향. CF '아이템-태그' 프로필 행렬의 기반
CREATE TABLE IF NOT EXISTS FoodTag (
    food_id  INTEGER NOT NULL,
    tag_id   INTEGER NOT NULL,
    PRIMARY KEY (food_id, tag_id),
    FOREIGN KEY (food_id) REFERENCES Food(food_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)  REFERENCES Tag(tag_id)   ON DELETE CASCADE
);
-- 역방향: 특정 태그를 가진 음식 목록 조회
CREATE INDEX IF NOT EXISTS idx_foodtag_tag ON FoodTag(tag_id);

-- ── ③ 유저 행동 및 추천 데이터 (동적) ────────────────────────────
-- 추천 요청 1건 = 1행. 세션 내 태그 선택/음식 행동을 묶는 부모 키
CREATE TABLE IF NOT EXISTS RecommendationSession (
    session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,                          -- 추천을 요청한 유저
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,   -- 추천 요청 시각
    FOREIGN KEY (user_id) REFERENCES User(user_id)
);
CREATE INDEX IF NOT EXISTS idx_recsession_user ON RecommendationSession(user_id);

-- 유저가 선택한 태그를 1태그당 1행으로 기록 (세션당 N행)
CREATE TABLE IF NOT EXISTS UserTagSelection (
    selection_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER,                        -- 소속 추천 세션
    tag_id        INTEGER,                        -- 유저가 선택한 태그
    FOREIGN KEY (session_id) REFERENCES RecommendationSession(session_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)     REFERENCES Tag(tag_id)
);
CREATE INDEX IF NOT EXISTS idx_tagsel_session ON UserTagSelection(session_id);

-- 클릭/최종선택 음식 행동을 발생 시점마다 1행씩 기록 (세션당 N행).
-- 가중치(click=1, final_select=2)는 컬럼에 박지 않고 의미만 보존 →
-- 합산 시 쿼리에서 CASE WHEN 으로 매핑. 정책이 바뀌어도 로그 불변.
CREATE TABLE IF NOT EXISTS UserInteractionLog (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER,                         -- 소속 추천 세션
    food_id      INTEGER,                         -- 대상 음식
    action_type  TEXT NOT NULL
                 CHECK (action_type IN ('click', 'final_select')),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,  -- 발생 시각
    FOREIGN KEY (session_id) REFERENCES RecommendationSession(session_id) ON DELETE CASCADE,
    FOREIGN KEY (food_id)    REFERENCES Food(food_id)
);
CREATE INDEX IF NOT EXISTS idx_interaction_session ON UserInteractionLog(session_id);

-- (유저, 음식, 태그) 단위 사전 집계. 태그선택 × 음식행동 결합 시그널 누적.
-- 같은 조합은 항상 1행으로 유지하고 UPSERT (복합 PK).
CREATE TABLE IF NOT EXISTS UserFoodTagWeight (
    user_id       INTEGER NOT NULL,
    food_id       INTEGER NOT NULL,
    tag_id        INTEGER NOT NULL,
    total_weight  INTEGER NOT NULL DEFAULT 0,     -- 누적 가중치 (클릭+1 / 최종+2)
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP, -- 마지막 갱신 시각
    PRIMARY KEY (user_id, food_id, tag_id),
    FOREIGN KEY (user_id) REFERENCES User(user_id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES Food(food_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)  REFERENCES Tag(tag_id)   ON DELETE CASCADE
);

-- SQLite 는 ON UPDATE CURRENT_TIMESTAMP 를 지원하지 않으므로 트리거로 대체
CREATE TRIGGER IF NOT EXISTS trg_userfoodtagweight_updated_at
AFTER UPDATE ON UserFoodTagWeight
FOR EACH ROW BEGIN
    UPDATE UserFoodTagWeight
       SET updated_at = CURRENT_TIMESTAMP
     WHERE user_id = NEW.user_id
       AND food_id = NEW.food_id
       AND tag_id  = NEW.tag_id;
END;

-- ── ④ 칭호(Badge) 테이블 ─────────────────────────────────────────
-- docs/db/BADGE_SPEC.md. 추천 DB 와 동일 파일에 칭호 테이블을 둔다.
-- 칭호 정의(메타데이터). 운영자가 시드로 채우는 정적 테이블
CREATE TABLE IF NOT EXISTS Badge (
    badge_id     TEXT PRIMARY KEY,                 -- 의미 있는 문자열 코드 (예: spicy, ramen)
    category     TEXT NOT NULL
                 CHECK (category IN ('A', 'B', 'C', 'D', 'E')),  -- A맛속성/B장르/C음식/D행동/E메타
    name         TEXT NOT NULL,                    -- 표시명 (예: 칼칼함 마니아)
    icon         TEXT,                             -- 이모지 아이콘
    description  TEXT NOT NULL                     -- 획득 조건 설명 (UI 노출용)
);

-- 유저별 칭호 획득 상태. (user, badge) 단위 1행, UPSERT.
-- 획득 '이력'(earned_at)과 현재 '유효 여부'(is_active)를 분리 →
-- 조건 미달로 비활성화돼도 이력이 남는다. 활성 구간 보유 기간은 일(day) 단위 누적.
CREATE TABLE IF NOT EXISTS UserBadge (
    user_id          INTEGER NOT NULL,
    badge_id         TEXT NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 0,    -- 현재 유효(조건 충족) 여부. 미달 시 0
    earned_at        TEXT,                          -- 최초 획득 시각(이력, 한번 기록 후 비우지 않음)
    active_since     TEXT,                          -- 현재 활성 구간 시작. 비활성이면 NULL
    held_total_days  INTEGER NOT NULL DEFAULT 0,    -- 종료된 활성 구간 보유 기간 누적(일)
    PRIMARY KEY (user_id, badge_id),
    FOREIGN KEY (user_id)  REFERENCES User(user_id)   ON DELETE CASCADE,
    FOREIGN KEY (badge_id) REFERENCES Badge(badge_id) ON DELETE CASCADE
);
-- 마이페이지 도감(유저별 전체 칭호) 조회
CREATE INDEX IF NOT EXISTS idx_userbadge_user ON UserBadge(user_id);
"""

# 기존 DB 에 누락된 컬럼을 ALTER 로 추가하기 위한 마이그레이션 목록
# (table, column, type) — init 시 PRAGMA table_info 로 존재 여부 확인 후 추가
ADD_COLUMNS: list[tuple[str, str, str]] = [
    # 회원가입(비밀번호 로그인) 지원: 기존 recommend.db 의 User 에 비밀번호 해시 컬럼 추가
    ("User", "password_hash", "TEXT NOT NULL DEFAULT ''"),
]


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, col, coltype in ADD_COLUMNS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")


def init_db(db_path: Path = DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _apply_migrations(conn)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        init_db()
        print(f"[OK] {DB_PATH} 초기화 완료")
    except Exception as e:
        print(f"[X] 초기화 실패: {e}")
    input("\n계속하려면 Enter 키를 누르세요...")
