"""app.db 스키마 초기화. 추천 엔진 전용 DB.

docs/recommend/SPEC.md §3 (데이터베이스 스키마) 의 논리 테이블을 그대로 옮긴 것.
크롤링 결과(details.db / stores·menus·business_hours)는 별도 DB 라 ATTACH 로 참조한다.
SQLite 는 DB 간 FK 제약을 걸 수 없으므로, store_id 를 참조하는 컬럼
(menu_dish_map, GroupRestaurantPreferences, UserRestaurantFilters)은
details.db / stores(store_id) 를 논리적으로 가리키되 FK 로 강제하지 않는다.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = BACKEND_ROOT / "db" / "app.db"
DETAILS_DB_PATH = BACKEND_ROOT / "db" / "details.db"

SCHEMA = """
-- ── 유저 / 취향 레이어 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Users (
    user_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    -- 4 미각축 (-1.0~+1.0). 온도는 환경 전용이라 유저 프로필엔 없음 (SPEC §2.2)
    pref_spicy       REAL NOT NULL DEFAULT 0.0,
    pref_sweet       REAL NOT NULL DEFAULT 0.0,
    pref_salty       REAL NOT NULL DEFAULT 0.0,
    pref_oily        REAL NOT NULL DEFAULT 0.0,
    mbti_code        TEXT,                          -- 16 그룹 코드 (4축 이진화)
    onboarding_done  INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT
);

-- 암묵적 CF / 개인 소비 장부. 시간 감쇠(§10) + 개인 부스트(§7.4)의 근거
CREATE TABLE IF NOT EXISTS UserTagLogs (
    user_id           INTEGER NOT NULL,
    tag_name          TEXT NOT NULL,               -- dish_id(문자열) 또는 카테고리명
    cumulative_count  INTEGER NOT NULL DEFAULT 0,
    last_consumed_at  TEXT,
    PRIMARY KEY (user_id, tag_name),
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
);

-- ── 음식 / 키워드 레이어 ──────────────────────────────────────────
-- 좌표가 붙는 곳은 가게 메뉴가 아니라 추상 음식(dishes). 5축 (온도 포함)
CREATE TABLE IF NOT EXISTS dishes (
    dish_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    dish_name   TEXT NOT NULL UNIQUE,              -- 짜장면/탕수육/라멘/마라탕
    category    TEXT,                              -- 한식/중식/일식/양식/...
    spicy       REAL NOT NULL DEFAULT 0.0,
    sweet       REAL NOT NULL DEFAULT 0.0,
    salty       REAL NOT NULL DEFAULT 0.0,
    oily        REAL NOT NULL DEFAULT 0.0,
    temp        REAL NOT NULL DEFAULT 0.0          -- 차가움(-) ↔ 뜨거움(+)
);
CREATE INDEX IF NOT EXISTS idx_dishes_category ON dishes(category);

-- 정규화 다리: 크롤링 실메뉴(details.db) → 추상 음식
CREATE TABLE IF NOT EXISTS menu_dish_map (
    store_id    INTEGER NOT NULL,                  -- → details.db / stores(store_id) (FK 미강제)
    menu_name   TEXT NOT NULL,                     -- "프리미엄마라탕(소)" 등 원본 메뉴명
    dish_id     INTEGER NOT NULL,
    confidence  REAL,
    PRIMARY KEY (store_id, menu_name),
    FOREIGN KEY (dish_id) REFERENCES dishes(dish_id) ON DELETE CASCADE
);
-- 역추적용: 특정 음식을 파는 가게 목록 조회 (2단계 후보 생성)
CREATE INDEX IF NOT EXISTS idx_menu_dish_dish ON menu_dish_map(dish_id);

-- 상황/환경 키워드 가중치 (5축). #폭염은 w_temp 음수, #한파는 양수
CREATE TABLE IF NOT EXISTS ContextKeywords (
    keyword_name      TEXT PRIMARY KEY,            -- #스트레스 / #폭염 / #한파
    keyword_type      TEXT NOT NULL DEFAULT 'context'
                      CHECK (keyword_type IN ('direct_taste', 'context')),
    w_spicy           REAL NOT NULL DEFAULT 0.0,
    w_sweet           REAL NOT NULL DEFAULT 0.0,
    w_salty           REAL NOT NULL DEFAULT 0.0,
    w_oily            REAL NOT NULL DEFAULT 0.0,
    w_temp            REAL NOT NULL DEFAULT 0.0,
    settle_log_count  INTEGER NOT NULL DEFAULT 0
);

-- ── 집단지성(CF) / 제어 레이어 ───────────────────────────────────
-- 16그룹 × 음식점 주문 장부. 평점 없음, 주문 횟수만 (SPEC §7.5)
CREATE TABLE IF NOT EXISTS GroupRestaurantPreferences (
    mbti_code    TEXT NOT NULL,                    -- 16종 그룹 코드
    store_id     INTEGER NOT NULL,                 -- → details.db / stores (FK 미강제)
    dish_id      INTEGER NOT NULL,
    order_count  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (mbti_code, store_id, dish_id),
    FOREIGN KEY (dish_id) REFERENCES dishes(dish_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_grouppref_group ON GroupRestaurantPreferences(mbti_code);

-- 음식 개인 제어 (이퀄라이저)
CREATE TABLE IF NOT EXISTS UserNegativeFilters (
    user_id     INTEGER NOT NULL,
    dish_id     INTEGER NOT NULL,
    is_ban      INTEGER NOT NULL DEFAULT 0,
    penalty     REAL NOT NULL DEFAULT 1.0,         -- 0.0~1.0 감점 계수
    updated_at  TEXT,
    PRIMARY KEY (user_id, dish_id),
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (dish_id) REFERENCES dishes(dish_id) ON DELETE CASCADE
);

-- 음식점 개인 제어 (BAN/감점/선호 통합). coefficient: <1 감점 / 1 중립 / >1 선호
CREATE TABLE IF NOT EXISTS UserRestaurantFilters (
    user_id      INTEGER NOT NULL,
    store_id     INTEGER NOT NULL,                 -- → details.db / stores (FK 미강제)
    is_ban       INTEGER NOT NULL DEFAULT 0,
    coefficient  REAL NOT NULL DEFAULT 1.0,        -- 0.0~2.0
    updated_at   TEXT,
    PRIMARY KEY (user_id, store_id),
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
);

-- ── 자가 진화 레이어 ──────────────────────────────────────────────
-- 정산 버퍼. 낮 동안 순수 텍스트 적재 → 새벽 배치(§9)가 소비
CREATE TABLE IF NOT EXISTS KeywordUpdateBuffer (
    buffer_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    input_keyword     TEXT NOT NULL,
    selected_dish_id  INTEGER,
    track             TEXT CHECK (track IN ('A', 'B', 'C')),
    created_at        TEXT,
    FOREIGN KEY (selected_dish_id) REFERENCES dishes(dish_id) ON DELETE SET NULL
);
"""

# 기존 DB 에 누락된 컬럼을 ALTER 로 추가하기 위한 마이그레이션 목록
# (table, column, type) — init 시 PRAGMA table_info 로 존재 여부 확인 후 추가
ADD_COLUMNS: list[tuple[str, str, str]] = []


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
