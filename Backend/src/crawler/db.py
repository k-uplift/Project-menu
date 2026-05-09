"""details.db 스키마 초기화. stores / menus / business_hours 3개 테이블."""
from __future__ import annotations

import sqlite3
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = BACKEND_ROOT / "db" / "details.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    store_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    address         TEXT,
    naver_place_id  TEXT UNIQUE
);

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
    PRIMARY KEY (store_id, day_of_week),
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
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
