"""raw.db / raw_restaurants  →  restaurants.db / restaurants 정제."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
RAW_DB_PATH = BACKEND_ROOT / "db" / "raw.db"
DEST_DB_PATH = BACKEND_ROOT / "db" / "restaurants.db"

OPEN_TEAM_CODE = "3070000"      # 성북구
OPEN_STATE_CODE = "01"          # 영업/정상
TARGET_DONGS = [
    "삼선동1가", "삼선동2가", "삼선동3가", "삼선동4가", "삼선동5가",
    "동소문동2가", "동소문동3가", "동소문동5가",
]


def clean(
    raw_db_path: Path = RAW_DB_PATH,
    dest_db_path: Path = DEST_DB_PATH,
) -> None:
    if not raw_db_path.exists():
        print(f"[X] raw DB 없음: {raw_db_path}\n   먼저 fetch.py를 실행하세요.", file=sys.stderr)
        sys.exit(1)

    dest_db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(dest_db_path)
    try:
        conn.execute(f"ATTACH DATABASE '{raw_db_path.as_posix()}' AS raw")

        cur = conn.execute('SELECT name FROM raw.sqlite_master WHERE type="table" AND name="raw_restaurants"')
        if cur.fetchone() is None:
            print("[X] raw.raw_restaurants 테이블이 없습니다.", file=sys.stderr)
            sys.exit(1)

        cur = conn.execute('PRAGMA raw.table_info(raw_restaurants)')
        columns = [row[1] for row in cur.fetchall()]
        cols_quoted = ", ".join(f'"{c}"' for c in columns)

        like_clause = " OR ".join(["SITEWHLADDR LIKE ?"] * len(TARGET_DONGS))
        params = [f"%{d}%" for d in TARGET_DONGS]

        conn.execute("DROP TABLE IF EXISTS restaurants")
        conn.execute(
            f"""
            CREATE TABLE restaurants AS
            SELECT {cols_quoted}
              FROM raw.raw_restaurants
             WHERE OPNSFTEAMCODE = ?
               AND TRDSTATEGBN = ?
               AND ({like_clause})
            """,
            [OPEN_TEAM_CODE, OPEN_STATE_CODE, *params],
        )
        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM raw.raw_restaurants").fetchone()[0]
        kept = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
        print(f"raw.db / raw_restaurants    : {total:,}건")
        print(f"restaurants.db / restaurants: {kept:,}건 (성북구 영업중 + 지정 동)")

        conn.execute("DETACH DATABASE raw")
    finally:
        conn.close()


if __name__ == "__main__":
    clean()
