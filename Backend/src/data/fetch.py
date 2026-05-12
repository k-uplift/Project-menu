"""서울시 일반음식점 인허가 정보(LOCALDATA_072404) 전체 수집 → SQLite raw 테이블 저장."""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean import clean as run_clean

API_BASE = "http://openapi.seoul.go.kr:8088"
SERVICE = "LOCALDATA_072404"
BATCH_SIZE = 1000
REQUEST_TIMEOUT = 30
RETRY_DELAY = 5
MAX_RETRY = 3
THROTTLE = 0.1

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = BACKEND_ROOT / "db" / "raw.db"
ENV_PATH = BACKEND_ROOT / ".env"

COLUMNS = [
    "OPNSFTEAMCODE", "MGTNO", "APVPERMYMD",
    "TRDSTATEGBN", "TRDSTATENM",
    "DTLSTATEGBN", "DTLSTATENM",
    "DCBYMD",
    "SITETEL", "SITEAREA", "SITEPOSTNO",
    "SITEWHLADDR", "RDNWHLADDR", "RDNPOSTNO",
    "BPLCNM", "LASTMODTS", "UPDATEGBN", "UPDATEDT",
    "UPTAENM", "X", "Y",
    "SNTUPTAENM", "MANEIPCNT", "WMEIPCNT",
    "TRDPJUBNSENM", "LVSENM", "WTRSPLYFACILSENM",
    "HOFFEPCNT", "FCTYOWKEPCNT", "FCTYSILJOBEPCNT", "FCTYPDTJOBEPCNT",
    "BDNGOWNSENM", "ISREAM", "MONAM",
    "MULTUSNUPSOYN", "FACILTOTSCP",
    "JTUPSOASGNNO", "JTUPSOMAINEDF", "HOMEPAGE",
]


def load_api_key() -> str:
    load_dotenv(ENV_PATH)
    key = os.getenv("KEY")
    if not key:
        raise RuntimeError(f"KEY가 {ENV_PATH}에 설정되어 있지 않습니다.")
    return key.strip()


def request_batch(api_key: str, start: int, end: int) -> dict:
    url = f"{API_BASE}/{api_key}/json/{SERVICE}/{start}/{end}/"
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    body = payload.get(SERVICE)
    if body is None:
        # 인증 실패 등은 최상위에 RESULT만 반환되기도 함
        result = payload.get("RESULT", {})
        raise RuntimeError(f"API 오류: {result.get('CODE')} {result.get('MESSAGE')}")
    return body


def fetch_total_count(api_key: str) -> int:
    body = request_batch(api_key, 1, 1)
    return int(body.get("list_total_count", 0))


def init_db(conn: sqlite3.Connection) -> None:
    cols_sql = ", ".join(f'"{c}" TEXT' for c in COLUMNS)
    conn.execute(
        f'CREATE TABLE IF NOT EXISTS raw_restaurants ({cols_sql}, PRIMARY KEY ("MGTNO"))'
    )
    conn.commit()


def insert_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    placeholders = ", ".join(["?"] * len(COLUMNS))
    cols_quoted = ", ".join(f'"{c}"' for c in COLUMNS)
    sql = f"INSERT OR REPLACE INTO raw_restaurants ({cols_quoted}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(r.get(c) for c in COLUMNS) for r in rows])


def fetch_with_retry(api_key: str, start: int, end: int) -> list[dict]:
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            body = request_batch(api_key, start, end)
            code = body.get("RESULT", {}).get("CODE", "")
            if code == "INFO-200":
                return []
            if code and code != "INFO-000":
                msg = body.get("RESULT", {}).get("MESSAGE", "")
                raise RuntimeError(f"{code} {msg}")
            return body.get("row", []) or []
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRY:
                print(f"  [재시도 {attempt}/{MAX_RETRY}] {start}~{end}: {e}")
                time.sleep(RETRY_DELAY)
    raise RuntimeError(f"{start}~{end} 최종 실패: {last_err}")


def main() -> None:
    api_key = load_api_key()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("총 데이터 개수 조회 중...")
    total = fetch_total_count(api_key)
    print(f"전체 데이터 개수: {total:,}건\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)

        saved = 0
        for start in range(1, total + 1, BATCH_SIZE):
            end = min(start + BATCH_SIZE - 1, total)
            try:
                rows = fetch_with_retry(api_key, start, end)
            except Exception as e:
                print(f"[X] {start:>7}~{end:>7} 스킵: {e}")
                continue
            insert_rows(conn, rows)
            conn.commit()
            saved += len(rows)
            pct = saved / total * 100 if total else 0
            print(f"  {start:>7}~{end:>7} | 누적 {saved:>7,}/{total:,} ({pct:5.1f}%)")
            time.sleep(THROTTLE)

        print(f"\n[완료] raw.db / raw_restaurants 테이블에 {saved:,}건 저장")
    finally:
        conn.close()

    print("\n--- 정제 단계 (restaurants.db 생성) ---")
    run_clean()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨", file=sys.stderr)
        sys.exit(130)
