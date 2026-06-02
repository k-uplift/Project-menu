"""추천 CF용 배경 사용자 더미 시드.

docs/demo/SCENARIO_DUMMY_DATA_SPEC.md §3 구현.
  - 비대치 태그쌍 8유형 × 유형당 3명 = User 24명
  - 1인 8건 final_select = 코어 5 + 소프트 2 + 노이즈 1 (총 192건)
  - 같은 유형 3명은 공통 코어 4 + 공통 소프트 1(=5건 공유) + 고유 3건 → 부분 겹침
  - created_at 을 쿨다운 3구간(>28일 / 14~28일 / <14일)에 분산
  - FoodTag(정적)은 건드리지 않음. User/RecommendationSession/UserInteractionLog 만 생성.

재실행 안전: email 이 '@demo' 로 끝나는 기존 더미를 먼저 삭제 후 다시 적재한다.

실행:  python -m src.data.database.seed_demo     (Backend/ 에서)
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # Backend/
from src.data.database.schema import DB_PATH, connect, init_db  # noqa: E402
from src.data.database.password import hash_password  # noqa: E402

# ── 유형 정의 (유형ID, 유형명, 태그A, 태그B) ───────────────────────────
TYPES: list[tuple[str, str, str, str]] = [
    ("T1", "매운국물파", "얼큰한", "국물있는"),
    ("T2", "튀김전러버", "고소한", "바삭한"),
    ("T3", "뜨끈보양파", "국물있는", "든든한"),
    ("T4", "진한메인파", "든든한", "진한"),
    ("T5", "단짠간식파", "달달한", "바삭한"),
    ("T6", "해장파", "국물있는", "해장"),
    ("T7", "슴슴든든파", "담백한", "든든한"),
    ("T8", "따뜻집밥파", "든든한", "따뜻한"),
]

USERS_PER_TYPE = 3
PICKS_PER_USER = 8
DEMO_PASSWORD = "demo1234"

# 8건의 created_at 오프셋(일). 4건>28일 / 2건 14~28일 / 2건<14일
DAY_OFFSETS = [60, 50, 40, 30, 24, 18, 10, 3]


def _load_food_tags(conn: sqlite3.Connection) -> dict[int, set[str]]:
    food_tags: dict[int, set[str]] = {}
    for fid, tag in conn.execute(
        "SELECT ft.food_id, t.tag_name FROM FoodTag ft JOIN Tag t ON t.tag_id = ft.tag_id"
    ):
        food_tags.setdefault(fid, set()).add(tag)
    return food_tags


def _pools(food_tags: dict[int, set[str]], a: str, b: str) -> tuple[list[int], list[int], list[int]]:
    """(코어, 소프트, 노이즈) food_id 리스트. food_id 오름차순(결정적)."""
    core, soft, noise = [], [], []
    for fid in sorted(food_tags):
        tags = food_tags[fid]
        has_a, has_b = a in tags, b in tags
        if has_a and has_b:
            core.append(fid)
        elif has_a or has_b:
            soft.append(fid)
        else:
            noise.append(fid)
    return core, soft, noise


def _pick_for_user(core: list[int], soft: list[int], noise: list[int], i: int) -> list[int]:
    """유형 내 i번째(0~2) 사용자의 8건 food_id.

    공통 코어 4 + 고유 코어 1 + 공통 소프트 1 + 고유 소프트 1 + 고유 노이즈 1.
    → 3명이 5건(코어4+소프트1)을 공유하고 3건은 서로 다름 (목표 Jaccard ≈ 0.45).
    풀이 작으면 순환 인덱스로 보충(코어 중복 허용).
    """
    def at(pool: list[int], idx: int) -> int:
        return pool[idx % len(pool)]

    picks: list[int] = []
    picks += core[:4]                     # 공통 코어 4
    picks.append(at(core, 4 + i))         # 고유 코어 1
    if soft:
        picks.append(soft[0])             # 공통 소프트 1
        picks.append(at(soft, 1 + i))     # 고유 소프트 1
    if noise:
        picks.append(at(noise, i))        # 고유 노이즈 1

    # 중복 제거(순서 유지) 후 8건까지 코어로 보충
    seen: set[int] = set()
    uniq = [p for p in picks if not (p in seen or seen.add(p))]
    j = 0
    while len(uniq) < PICKS_PER_USER and core:
        cand = at(core, j)
        if cand not in seen:
            uniq.append(cand)
            seen.add(cand)
        j += 1
    return uniq[:PICKS_PER_USER]


def _clear_demo(conn: sqlite3.Connection) -> None:
    """email 이 '@demo' 로 끝나는 더미와 그 세션/로그 삭제(순서 중요)."""
    rows = conn.execute("SELECT user_id FROM User WHERE email LIKE '%@demo'").fetchall()
    uids = [r[0] for r in rows]
    if not uids:
        return
    qs = ",".join("?" * len(uids))
    conn.execute(
        f"DELETE FROM UserInteractionLog WHERE session_id IN "
        f"(SELECT session_id FROM RecommendationSession WHERE user_id IN ({qs}))",
        uids,
    )
    conn.execute(f"DELETE FROM RecommendationSession WHERE user_id IN ({qs})", uids)
    conn.execute(f"DELETE FROM User WHERE user_id IN ({qs})", uids)


def seed(db_path: Path = DB_PATH, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    init_db(db_path)
    conn = connect(db_path)
    try:
        food_tags = _load_food_tags(conn)
        if not food_tags:
            raise RuntimeError("FoodTag 가 비어 있음. 먼저 load_recommend.py 로 카탈로그를 적재하세요.")

        _clear_demo(conn)
        pw_hash = hash_password(DEMO_PASSWORD)  # 데모 계정 공통 비밀번호

        user_foods: dict[str, set[int]] = {}      # email -> food_id set (검증용)
        user_type: dict[str, str] = {}
        n_users = n_logs = 0

        for tid, _name, a, b in TYPES:
            core, soft, noise = _pools(food_tags, a, b)
            for i in range(USERS_PER_TYPE):
                email = f"{tid.lower()}_u{i + 1}@demo"
                cur = conn.execute(
                    "INSERT INTO User(email, password_hash) VALUES (?, ?)", (email, pw_hash)
                )
                uid = cur.lastrowid
                picks = _pick_for_user(core, soft, noise, i)
                for off, fid in zip(DAY_OFFSETS, picks):
                    ts = (now - timedelta(days=off)).strftime("%Y-%m-%d %H:%M:%S")
                    s = conn.execute(
                        "INSERT INTO RecommendationSession(user_id, created_at) VALUES (?, ?)",
                        (uid, ts),
                    )
                    conn.execute(
                        "INSERT INTO UserInteractionLog(session_id, food_id, action_type, created_at) "
                        "VALUES (?, ?, 'final_select', ?)",
                        (s.lastrowid, fid, ts),
                    )
                    n_logs += 1
                user_foods[email] = set(picks)
                user_type[email] = tid
                n_users += 1

        conn.commit()
        return {"users": n_users, "logs": n_logs, "user_foods": user_foods, "user_type": user_type}
    finally:
        conn.close()


def _jaccard(x: set[int], y: set[int]) -> float:
    return len(x & y) / len(x | y) if (x or y) else 0.0


def _validate(result: dict) -> None:
    """같은 유형 평균 Jaccard ≈ 0.4~0.6, 다른 유형 < 0.2 검증 리포트."""
    uf, ut = result["user_foods"], result["user_type"]
    by_type: dict[str, list[str]] = {}
    for email, tid in ut.items():
        by_type.setdefault(tid, []).append(email)

    print("\n[검증] 같은 유형 내 평균 Jaccard")
    within_all = []
    for tid, emails in by_type.items():
        pairs = [
            _jaccard(uf[emails[m]], uf[emails[n]])
            for m in range(len(emails))
            for n in range(m + 1, len(emails))
        ]
        avg = sum(pairs) / len(pairs) if pairs else 0.0
        within_all.extend(pairs)
        flag = "OK" if 0.4 <= avg <= 0.6 else "확인"
        print(f"  {tid}: {avg:.2f}  [{flag}]")

    emails = list(uf)
    cross = [
        _jaccard(uf[emails[m]], uf[emails[n]])
        for m in range(len(emails))
        for n in range(m + 1, len(emails))
        if ut[emails[m]] != ut[emails[n]]
    ]
    win_avg = sum(within_all) / len(within_all) if within_all else 0.0
    cross_avg = sum(cross) / len(cross) if cross else 0.0
    print(f"\n  전체 같은유형 평균: {win_avg:.2f} (목표 0.4~0.6)")
    print(f"  전체 다른유형 평균: {cross_avg:.2f} (목표 < 0.2)")


if __name__ == "__main__":
    try:
        res = seed()
        print(f"[OK] User {res['users']}명 / 행동로그 {res['logs']}건 적재 완료 → {DB_PATH}")
        _validate(res)
    except Exception as e:  # noqa: BLE001
        print(f"[X] 시드 실패: {e}")
        raise
