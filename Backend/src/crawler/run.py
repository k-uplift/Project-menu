"""restaurants.db 의 BPLCNM 으로 네이버 검색 → 메뉴/영업시간 → details.db 저장.

흐름:
  1. restaurants.db / restaurants 에서 BPLCNM, RDNWHLADDR/SITEWHLADDR 읽기
  2. (Playwright 브라우저 1개로 전체 처리)
  3. search.find_place_id 로 place_id 획득
  4. detail.fetch_detail 로 메뉴 / 영업시간 가져오기
  5. details.db 의 stores / menus / business_hours 에 저장

이미 stores 에 있는 (naver_place_id) 는 스킵 — 재실행 가능.

환경변수:
  HEADLESS=0  → 브라우저 창 보기 (디버깅)
  DEBUG=1     → 모든 가게에 대해 디버그 출력
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import DB_PATH as DETAILS_DB_PATH, init_db, connect
from search import find_place_id
from detail import fetch_detail, PlaceDetail
from browser import browser_session
from coord import parse_tm

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DB_PATH = BACKEND_ROOT / "db" / "restaurants.db"

THROTTLE = 1.5      # 가게 1건 처리 후 대기 (네이버 차단 회피, Playwright 라 좀 여유롭게)
MAX_FAIL = 20       # 연속 실패 N건이면 중단


def load_source_stores(
    limit: int | None = None,
) -> list[tuple[str, str, str, str, str]]:
    """(MGTNO, BPLCNM, 주소, X, Y) 튜플. 좌표는 raw TM 문자열."""
    if not SOURCE_DB_PATH.exists():
        print(f"[X] {SOURCE_DB_PATH} 없음. 먼저 fetch.py / clean.py 실행.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(SOURCE_DB_PATH)
    try:
        sql = """
            SELECT MGTNO, BPLCNM,
                   COALESCE(NULLIF(TRIM(RDNWHLADDR), ''), SITEWHLADDR) AS addr,
                   X, Y
              FROM restaurants
             WHERE BPLCNM IS NOT NULL AND TRIM(BPLCNM) != ''
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [
            (r[0], r[1], r[2] or "", r[3] or "", r[4] or "")
            for r in conn.execute(sql).fetchall()
        ]
    finally:
        conn.close()


def get_existing_place_id(conn: sqlite3.Connection, mgtno: str) -> str | None:
    """이 mgtno 가 이미 네이버 place_id 와 매칭되어 있으면 그 pid 반환."""
    row = conn.execute(
        "SELECT naver_place_id FROM stores "
        " WHERE mgtno = ? AND naver_place_id IS NOT NULL AND naver_place_id != ''",
        (mgtno,),
    ).fetchone()
    return row[0] if row else None


def upsert_store(
    conn: sqlite3.Connection,
    mgtno: str,
    name: str,
    address: str,
    place_id: str,
) -> int:
    """mgtno 기준 upsert.

    같은 mgtno 가 있으면 store_id 재사용 + 매칭된 place_id/이름/주소가 바뀌었으면 UPDATE.
    없으면 INSERT 후 새 store_id 반환.
    """
    cur = conn.execute(
        "SELECT store_id, naver_place_id FROM stores WHERE mgtno = ?", (mgtno,)
    )
    row = cur.fetchone()
    if row:
        store_id, prev_pid = row
        if prev_pid != place_id:
            conn.execute(
                "UPDATE stores SET naver_place_id = ?, name = ?, address = ? "
                "WHERE store_id = ?",
                (place_id, name, address, store_id),
            )
        return store_id

    cur = conn.execute(
        "INSERT INTO stores (mgtno, name, address, naver_place_id) "
        "VALUES (?, ?, ?, ?)",
        (mgtno, name, address, place_id),
    )
    return cur.lastrowid


def replace_menus(conn: sqlite3.Connection, store_id: int, detail: PlaceDetail) -> None:
    conn.execute("DELETE FROM menus WHERE store_id = ?", (store_id,))
    if detail.menus:
        conn.executemany(
            "INSERT INTO menus (store_id, menu_name, price) VALUES (?, ?, ?)",
            [(store_id, m.name, m.price) for m in detail.menus],
        )


def replace_hours(conn: sqlite3.Connection, store_id: int, detail: PlaceDetail) -> None:
    conn.execute("DELETE FROM business_hours WHERE store_id = ?", (store_id,))
    if detail.hours:
        conn.executemany(
            """INSERT INTO business_hours
               (store_id, day_of_week, open_time, close_time, is_closed,
                break_start, break_end, last_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (store_id, h.day_of_week, h.open_time, h.close_time, int(h.is_closed),
                 h.break_start, h.break_end, h.last_order)
                for h in detail.hours
            ],
        )


def main(limit: int | None = None) -> None:
    init_db(DETAILS_DB_PATH)
    sources = load_source_stores(limit=limit)
    print(f"대상 가게 수: {len(sources):,}")

    consecutive_fail = 0
    success = 0
    skipped_no_pid = 0

    conn = connect(DETAILS_DB_PATH)
    reused = 0
    try:
        with browser_session() as page:
            for i, (mgtno, name, address, x_raw, y_raw) in enumerate(sources, 1):
                print(f"[{i:>4}/{len(sources)}] {name}")

                # 첫 번째 가게는 항상 디버그 출력 — 응답/DOM 구조 확인용
                verbose = (i == 1)

                # 0) 이미 매칭된 place_id 가 있으면 검색 단계 스킵
                existing_pid = get_existing_place_id(conn, mgtno)
                if existing_pid:
                    place_id = existing_pid
                    matched_name = name
                    print(f"  → 기존 매칭 재사용 (place_id={place_id})")
                    reused += 1
                else:
                    source_lnglat = parse_tm(x_raw, y_raw)
                    cand = find_place_id(
                        name, page=page,
                        source_address=address,
                        source_lnglat=source_lnglat,
                        verbose=verbose,
                    )
                    if cand is None or not cand.get("id"):
                        print(f"  → place_id 못 찾음 (또는 위치 불일치)")
                        skipped_no_pid += 1
                        consecutive_fail += 1
                        if consecutive_fail >= MAX_FAIL:
                            print(f"\n[중단] 연속 {MAX_FAIL}건 실패 — 차단 의심", file=sys.stderr)
                            break
                        time.sleep(THROTTLE)
                        continue
                    place_id = cand["id"]
                    matched_name = cand["name"]

                detail = fetch_detail(place_id, page=page, verbose=verbose)

                store_id = upsert_store(conn, mgtno, name, address, place_id)
                replace_menus(conn, store_id, detail)
                replace_hours(conn, store_id, detail)
                conn.commit()

                print(f"  → store_id={store_id} (place_id={place_id}, 매칭='{matched_name}'), "
                      f"메뉴 {len(detail.menus)}, 영업시간 {len(detail.hours)}")
                success += 1
                consecutive_fail = 0
                time.sleep(THROTTLE)

        print(f"\n[완료] 성공 {success}건 (기존 매칭 재사용 {reused}건), "
              f"place_id 못찾음 {skipped_no_pid}건")
    finally:
        conn.close()


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    try:
        main(limit=lim)
    except KeyboardInterrupt:
        print("\n중단됨", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\n[X] 예외: {e}", file=sys.stderr)
    input("\n계속하려면 Enter 키를 누르세요...")
