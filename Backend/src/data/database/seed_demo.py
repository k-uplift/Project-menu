"""추천 CF용 배경 사용자 더미 시드.

docs/demo/SCENARIO_DUMMY_DATA_SPEC.md §3 구현.
  - 비대치 태그쌍 8유형 × 유형당 3명 = User 24명
  - 1인 8건 final_select = 코어 5 + 소프트 2 + 노이즈 1 (총 192건)
  - 같은 유형 3명은 공통 코어 4 + 공통 소프트 1(=5건 공유) + 고유 3건 → 부분 겹침
  - created_at 을 쿨다운 3구간(>28일 / 14~28일 / <14일)에 분산
  - FoodTag(정적)은 건드리지 않음. User/RecommendationSession/UserTagSelection/UserInteractionLog 생성.
  - 각 세션의 input_tags = 그 유형의 (a, b) 태그 쌍 → UserTagSelection 2행/세션 (총 384행).
    cf_module Tab1이 세션 vs 세션 Jaccard에 쓰는 데이터.

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
PICKS_PER_USER = 8       # 기존 호환 — 한 세션당 음식 수가 아니라 *기본 모드* 한 사람당 final 수
CLICKS_PER_USER = 5      # 확장 모드: 사용자당 click 5건 (관심만 보이고 final 안 한 행동) — Tab2 신호 다양화
DEMO_PASSWORD = "demo1234"

# 기존 8건 오프셋 — 호환용. 확장 모드에서는 _day_offset() 헬퍼가 N 세션에 균등 분산.
DAY_OFFSETS = [60, 50, 40, 30, 24, 18, 10, 3]

# 확장 모드 — Tab1 도배 해소 + CF 임팩트용. 사용자당 세션 N 으로 늘리고 입력 태그 다양화.
# 모든 시드 14 안에서 (a, b) 외 다른 시드도 변종으로 섞음.
SEED_TAGS_ALL = [
    "따뜻한", "시원한", "얼큰한", "국물있는", "담백한", "진한", "가벼운",
    "든든한", "해장", "야식", "바삭한", "쫄깃한", "고소한", "달달한",
]


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


def _pick_for_user(
    core: list[int], soft: list[int], noise: list[int], i: int,
    type_offset: int = 0, n: int = PICKS_PER_USER,
) -> list[int]:
    """유형 내 i번째(0~2) 사용자의 final food_id N건.

    공통 코어 4 + 고유 코어 1 + 공통 소프트 1 + 고유 소프트 1 + 고유 노이즈 1.
    → 3명이 5건(코어4+소프트1)을 공유하고 3건은 서로 다름 (목표 Jaccard ≈ 0.45).
    풀이 작으면 순환 인덱스로 보충(코어 중복 허용).

    type_offset: 유형별 core 시작 인덱스 시프트. food_id 작은 음식이 *모든 유형*
        의 공통 코어에 들어가 *kind 도배*를 만들던 결함을 시정. 같은 유형 안에서는
        type_offset 이 같아 *유형 내 Jaccard 0.4~0.6 유지*는 그대로.
    n: 총 final 행동 수. 기본 8, 확장 모드는 32 정도.
    """
    def at(pool: list[int], idx: int) -> int:
        return pool[idx % len(pool)]

    picks: list[int] = []
    # 공통 코어 4 — 유형 offset 적용해 food_id 분포 분산
    for j in range(4):
        picks.append(at(core, type_offset + j))
    picks.append(at(core, type_offset + 4 + i))   # 고유 코어 1
    if soft:
        picks.append(at(soft, type_offset))       # 공통 소프트 1
        picks.append(at(soft, type_offset + 1 + i))  # 고유 소프트 1
    if noise:
        picks.append(at(noise, type_offset + i))  # 고유 노이즈 1

    # 중복 제거(순서 유지) 후 n건까지 보충 — *사용자 i 별로 다른 시작점* 으로 다양화
    # n=8 기본 모드는 위에서 거의 채워져 보충이 적고, n=32 확장 모드는 28건이 여기서 채워짐
    seen: set[int] = set()
    uniq = [p for p in picks if not (p in seen or seen.add(p))]
    # 풀 우선순위: core(가장 강한 매치) → soft → noise
    extras = list(core) + list(soft) + list(noise)
    # 사용자 i 별로 다른 시작점 — 같은 유형 3명이 *동일한 보충 음식* 가지지 않도록
    user_seed = (type_offset + 7 * (i + 1)) % max(1, len(extras))
    j = 0
    while len(uniq) < n and extras:
        cand = at(extras, user_seed + j)
        if cand not in seen:
            uniq.append(cand)
            seen.add(cand)
        j += 1
        if j > 4 * len(extras):  # 안전 — 풀 너무 작아 못 채울 때
            break
    return uniq[:n]


def _day_offset(idx: int, n: int) -> int:
    """N 세션을 [3, 60]일 사이로 균등 분산. 기존 DAY_OFFSETS 와 거의 호환."""
    if n <= 1:
        return 30
    # 최근(3일)부터 오래된(60일)까지
    return int(3 + (60 - 3) * (n - 1 - idx) / (n - 1))


def _session_tags(a: str, b: str, idx: int, n: int) -> tuple[str, str]:
    """세션마다 입력 태그 변종 — Tab1 세션 다양성 확보.

    절반은 (a, b) 그대로 (유형 정체성), 나머지는 (a, x) 또는 (b, y) 로 변종.
    x, y 는 시드 14 안의 *다른 시드* 중 결정적 선택 (seed_idx 기반 회전).
    """
    base_count = n // 2
    if idx < base_count:
        return a, b
    # 변종 풀 — a, b 자기 자신 제외
    others = [t for t in SEED_TAGS_ALL if t not in (a, b)]
    pick_idx = (idx - base_count) % len(others)
    other = others[pick_idx]
    # 절반은 a 기반, 절반은 b 기반
    if (idx - base_count) % 2 == 0:
        return a, other
    return b, other


def _clear_demo(conn: sqlite3.Connection) -> None:
    """더미 사용자 + 세션/로그 삭제 + sqlite_sequence 리셋 (순서 중요).

    삭제 대상:
      - email LIKE '%@demo' (T1~T8 더미)
      - email LIKE 'demo%@menu.local' (ensure_demo_user 가 만든 데모)

    sqlite_sequence 를 리셋해 다음 seed_demo 가 user_id 를 항상 1 부터 채번하도록.
    UserFoodTagWeight 도 통째로 비움 (정책 변경 또는 누적 흔적 정리).
    """
    rows = conn.execute(
        "SELECT user_id FROM User WHERE email LIKE '%@demo' OR email LIKE 'demo%@menu.local'"
    ).fetchall()
    uids = [r[0] for r in rows]
    if uids:
        qs = ",".join("?" * len(uids))
        conn.execute(
            f"DELETE FROM UserInteractionLog WHERE session_id IN "
            f"(SELECT session_id FROM RecommendationSession WHERE user_id IN ({qs}))",
            uids,
        )
        conn.execute(
            f"DELETE FROM UserTagSelection WHERE session_id IN "
            f"(SELECT session_id FROM RecommendationSession WHERE user_id IN ({qs}))",
            uids,
        )
        conn.execute(f"DELETE FROM UserFoodTagWeight WHERE user_id IN ({qs})", uids)
        conn.execute(f"DELETE FROM RecommendationSession WHERE user_id IN ({qs})", uids)
        conn.execute(f"DELETE FROM User WHERE user_id IN ({qs})", uids)

    # AUTOINCREMENT 리셋 — User·RecommendationSession·UserInteractionLog·UserTagSelection 다 1 부터
    for table in ("User", "RecommendationSession", "UserInteractionLog", "UserTagSelection"):
        conn.execute("UPDATE sqlite_sequence SET seq = 0 WHERE name = ?", (table,))


def seed(
    db_path: Path = DB_PATH,
    now: datetime | None = None,
    sessions_per_user: int = PICKS_PER_USER,
    use_type_offset: bool = False,
    variants: bool = False,
    users_per_type: int = USERS_PER_TYPE,
    clicks_per_user: int = 0,
) -> dict:
    """더미 시드.

    기본 호출(인자 0): 24명 × 8 세션 = 192건 (기세웅 원본 동작 유지).
    확장 모드 (--extended): sessions_per_user=32, type_offset=True, variants=True
        → 24명 × 32 세션 = 768 final. Tab1 도배 해소 + Tab2 임팩트 ↑.
    *대확장* 모드 (--big): users_per_type=10, clicks_per_user=5
        → 80명 × (32 final + 5 click) = 2,960 행동. 유사 사용자 풀 *대폭 확장*.

    click 행동은 별도 세션 (final 과 분리). soft 풀 음식에 click — '관심만 보임' 모사.
    """
    now = now or datetime.now()
    init_db(db_path)
    conn = connect(db_path)
    try:
        food_tags = _load_food_tags(conn)
        if not food_tags:
            raise RuntimeError("FoodTag 가 비어 있음. 먼저 load_recommend.py 로 카탈로그를 적재하세요.")

        # Tag name → tag_id 매핑. 각 유형의 (a, b) 태그 쌍을 UserTagSelection에 넣을 때 사용.
        tag_name_to_id = {name: tid for name, tid in conn.execute("SELECT tag_name, tag_id FROM Tag")}

        _clear_demo(conn)
        pw_hash = hash_password(DEMO_PASSWORD)  # 데모 계정 공통 비밀번호

        user_foods: dict[str, set[int]] = {}      # email -> food_id set (검증용)
        user_type: dict[str, str] = {}
        n_users = n_logs = n_tag_sels = n_clicks = 0

        for type_idx, (tid, _name, a, b) in enumerate(TYPES):
            core, soft, noise = _pools(food_tags, a, b)
            a_id, b_id = tag_name_to_id[a], tag_name_to_id[b]
            type_offset = (type_idx * 3) if use_type_offset else 0
            for i in range(users_per_type):
                email = f"{tid.lower()}_u{i + 1}@demo"
                cur = conn.execute(
                    "INSERT INTO User(email, password_hash) VALUES (?, ?)", (email, pw_hash)
                )
                uid = cur.lastrowid
                picks = _pick_for_user(core, soft, noise, i,
                                       type_offset=type_offset, n=sessions_per_user)
                for sess_idx, fid in enumerate(picks):
                    off = _day_offset(sess_idx, len(picks))
                    ts = (now - timedelta(days=off)).strftime("%Y-%m-%d %H:%M:%S")
                    s = conn.execute(
                        "INSERT INTO RecommendationSession(user_id, created_at) VALUES (?, ?)",
                        (uid, ts),
                    )
                    sid = s.lastrowid
                    # 이 세션이 검색한 태그. 기본은 (a, b), variants 모드는 변종 섞음.
                    if variants:
                        ta, tb = _session_tags(a, b, sess_idx, len(picks))
                    else:
                        ta, tb = a, b
                    ta_id = tag_name_to_id.get(ta, a_id)
                    tb_id = tag_name_to_id.get(tb, b_id)
                    conn.executemany(
                        "INSERT INTO UserTagSelection(session_id, tag_id) VALUES (?, ?)",
                        [(sid, ta_id), (sid, tb_id)],
                    )
                    conn.execute(
                        "INSERT INTO UserInteractionLog(session_id, food_id, action_type, created_at) "
                        "VALUES (?, ?, 'final_select', ?)",
                        (sid, fid, ts),
                    )
                    n_logs += 1
                    n_tag_sels += 2
                # click 행동 — 별도 세션. soft 풀에서 회전 선택 (관심만 보인 음식)
                if clicks_per_user > 0 and soft:
                    for c_idx in range(clicks_per_user):
                        click_fid = soft[(type_offset + i * 7 + c_idx) % len(soft)]
                        # 최근 시각 (click 은 더 최신 행동으로 — 활성 사용자 모사)
                        off = c_idx * 2 + 1
                        ts = (now - timedelta(days=off)).strftime("%Y-%m-%d %H:%M:%S")
                        s = conn.execute(
                            "INSERT INTO RecommendationSession(user_id, created_at) VALUES (?, ?)",
                            (uid, ts),
                        )
                        sid = s.lastrowid
                        conn.executemany(
                            "INSERT INTO UserTagSelection(session_id, tag_id) VALUES (?, ?)",
                            [(sid, a_id), (sid, b_id)],
                        )
                        conn.execute(
                            "INSERT INTO UserInteractionLog(session_id, food_id, action_type, created_at) "
                            "VALUES (?, ?, 'click', ?)",
                            (sid, click_fid, ts),
                        )
                        n_clicks += 1
                        n_tag_sels += 2

                user_foods[email] = set(picks)
                user_type[email] = tid
                n_users += 1

        conn.commit()
        return {"users": n_users, "logs": n_logs, "clicks": n_clicks,
                "tag_selections": n_tag_sels,
                "user_foods": user_foods, "user_type": user_type}
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--extended", action="store_true",
                        help="확장 모드 — 사용자당 32 세션 + type_offset + variants. Tab1 도배 해소용.")
    parser.add_argument("--big", action="store_true",
                        help="대확장 모드 — extended + users_per_type=10 + clicks_per_user=5. "
                             "80명 × (32 final + 5 click) = 2,960 행동. Tab2 임팩트 대폭↑.")
    parser.add_argument("--sessions", type=int, default=None,
                        help="사용자당 세션 수 (기본 8). --extended/--big 와 함께면 기본 32.")
    parser.add_argument("--users-per-type", type=int, default=None,
                        help="유형당 사용자 수 (기본 3). --big 면 10.")
    parser.add_argument("--clicks", type=int, default=None,
                        help="사용자당 click 행동 수 (기본 0). --big 면 5.")
    args = parser.parse_args()

    use_extended = args.extended or args.big

    sessions = args.sessions
    if use_extended and sessions is None:
        sessions = 32
    if sessions is None:
        sessions = PICKS_PER_USER

    users_per_type = args.users_per_type
    if users_per_type is None:
        users_per_type = 10 if args.big else USERS_PER_TYPE

    clicks = args.clicks
    if clicks is None:
        clicks = 5 if args.big else 0

    try:
        res = seed(
            sessions_per_user=sessions,
            use_type_offset=use_extended,
            variants=use_extended,
            users_per_type=users_per_type,
            clicks_per_user=clicks,
        )
        if args.big:
            mode = "대확장"
        elif args.extended:
            mode = "확장"
        else:
            mode = "기본"
        print(f"[OK] {mode} 모드 / User {res['users']}명 "
              f"/ final {res['logs']}건 / click {res.get('clicks', 0)}건 "
              f"/ 태그선택 {res['tag_selections']}건 → {DB_PATH}")
        _validate(res)
    except Exception as e:  # noqa: BLE001
        print(f"[X] 시드 실패: {e}")
        raise
