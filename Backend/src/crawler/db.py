"""details.db 스키마 초기화. stores / menus / business_hours 3개 테이블."""
from __future__ import annotations

import sqlite3
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = BACKEND_ROOT / "db" / "details.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    store_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    mgtno           TEXT UNIQUE,
    name            TEXT NOT NULL,
    address         TEXT,
    naver_place_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_stores_place ON stores(naver_place_id);

CREATE TABLE IF NOT EXISTS menus (
    store_id    INTEGER NOT NULL,
    menu_name   TEXT NOT NULL,
    price       TEXT,
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_menus_store ON menus(store_id);

CREATE TABLE IF NOT EXISTS business_hours (
    store_id     INTEGER NOT NULL,
    day_of_week  TEXT NOT NULL,
    open_time    TEXT,
    close_time   TEXT,
    is_closed    INTEGER NOT NULL DEFAULT 0,
    break_start  TEXT,
    break_end    TEXT,
    last_order   TEXT,
    PRIMARY KEY (store_id, day_of_week),
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);
"""

# 기존 DB 에 누락된 컬럼을 ALTER 로 추가하기 위한 마이그레이션 목록
ADD_COLUMNS: list[tuple[str, str, str]] = [
    ("business_hours", "break_start", "TEXT"),
    ("business_hours", "break_end",   "TEXT"),
    ("business_hours", "last_order",  "TEXT"),
    ("stores",         "mgtno",       "TEXT"),
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
