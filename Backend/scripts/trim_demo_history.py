"""시연용 명명 계정(Alice·Charlie·Bob)의 이력을 *시그니처 몇 개*로 재구성.

배경 (CF 시연 튜닝):
  cf_module 의 CF 탭(tab2)은 "사용자가 *이미 final_select 한* kind 는 후보에서 제외"한다
  (_filter_candidate_kinds — '아직 안 골라본 걸 추천'이 CF 의 의도). seed_demo 의 명명 계정은
  final_select 가 32~34개라 *자기 취향 kind 를 거의 다 소비*해, CF 후보가 텅 빈다.

해결 (옵션 ③ — 데이터 트리밍 / 재구성):
  Alice·Charlie·Bob 의 행동 이력을 페르소나 *보편 시그니처* 6개로 재설정해 CF 에 헤드룸을 준다.
  핵심: 시그니처는 *그 페르소나 전원이 공유하는 흔한 kind* 여야 한다. 그래야
    (1) 트리밍된 데모 계정이 full 페르소나 동료(공급원)들과 유사도 임계 위로 매칭되고,
    (2) full 동료들이 *시그니처 외* kind 를 final 해 둔 게 CF 후보로 풍부하게 떠오른다.
  - 나머지 77명(페르소나#N)은 *그대로* — CF 추천을 공급하는 쪽이라 풍부할수록 좋음.
  - 검색 태그(UserTagSelection)는 건드리지 않음 → 미식유형 진단 유지.
  - Alice·Charlie 는 시그니처 5개를 겹쳐 '서로 닮은 사용자' 데모 장면(≈71%) 보존.

방식: 결정적·재현 가능하도록 *해당 계정의 모든 행동 로그를 지우고 시그니처를 INSERT* 한다.
  (기존 final 을 남기는 방식은 seed 랜덤성에 따라 시그니처 kind 가 없을 수 있어 INSERT 로 보장.)
  로그는 그 계정의 첫 세션에 붙인다 — CF tab2 는 사용자 단위 집계라 세션 분산 불필요.
재실행 안전: 매번 같은 시그니처로 재설정. seed_demo 재적재 후 다시 돌리면 트리밍 상태 복원.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "recommend.db"

# user_id → (표시이름, 시그니처 음식 종류). 페르소나 전원이 공유하는 *흔한* kind 로 구성.
SIGNATURES: dict[int, tuple[str, list[str]]] = {
    1: ("Alice", ["짬뽕", "김치찌개", "감자탕", "곱창전골", "내장국밥", "갈비탕"]),
    2: ("Charlie", ["김치찌개", "감자탕", "곱창전골", "내장국밥", "갈비탕", "육개장"]),
    41: ("Bob", ["양념치킨", "쿠키", "크로플", "타르트", "닭꼬치", "돈까스"]),
}


def _food_id(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT food_id FROM Food WHERE food_name = ?", (name,)).fetchone()
    return row[0] if row else None


def _food_tag_ids(conn: sqlite3.Connection, food_id: int, limit: int = 3) -> list[int]:
    """그 음식(kind)의 대표 태그 tag_id 상위 N개 (FoodTag)."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT tag_id FROM FoodTag WHERE food_id = ? LIMIT ?", (food_id, limit)
        )
    ]


def trim(conn: sqlite3.Connection) -> None:
    for uid, (label, sig_names) in SIGNATURES.items():
        sessions = [
            r[0]
            for r in conn.execute(
                "SELECT session_id FROM RecommendationSession WHERE user_id = ? ORDER BY session_id",
                (uid,),
            )
        ]
        if not sessions:
            print(f"  ⚠️  user {uid} ({label}) 세션 없음 — 건너뜀")
            continue

        qmarks = ",".join("?" for _ in sessions)
        before = conn.execute(
            f"SELECT COUNT(*) FROM UserInteractionLog WHERE session_id IN ({qmarks})",
            sessions,
        ).fetchone()[0]

        # 1) 이 계정의 모든 행동 로그 삭제
        conn.execute(
            f"DELETE FROM UserInteractionLog WHERE session_id IN ({qmarks})", sessions
        )
        # 2) 시그니처를 *최근 세션들에 하나씩 분산* INSERT.
        #    sessions 는 session_id 오름차순 → 뒤쪽이 최근. 한 시그니처당 한 세션.
        #    이렇게 하면 '나의 먹거리 일기'(최근순)에 [태그 + 선택 음식]이 여러 칸으로 보인다.
        #    (CF 는 사용자 단위 집계라 세션 분산과 무관 — 유사도·제외·점수 모두 동일.)
        recent = sessions[-len(sig_names):] if len(sessions) >= len(sig_names) else sessions
        inserted = []
        for i, name in enumerate(sig_names):
            fid = _food_id(conn, name)
            if fid is None:
                print(f"  ⚠️  '{name}' Food 테이블에 없음 — 건너뜀")
                continue
            sess = recent[i % len(recent)]
            # 세션 시각을 하루씩 벌린다 — 같은 태그 음식들이 일기 dedup(같은 태그+근접
            # 시각 ≤120초)으로 *한 칸에 뭉치는 것* 방지. 음식마다 하나씩 칸이 나오게.
            # 최신 id(recent[-1])일수록 더 최근 시각이 되도록 오프셋 계산.
            day_off = len(recent) - 1 - i
            conn.execute(
                "UPDATE RecommendationSession SET created_at = datetime('now', ?) "
                "WHERE session_id = ?",
                (f"-{day_off} days", sess),
            )
            conn.execute(
                "INSERT INTO UserInteractionLog(session_id, food_id, action_type, created_at) "
                "VALUES (?, ?, 'final_select', datetime('now', ?))",
                (sess, fid, f"-{day_off} days"),
            )
            # 그 세션의 검색 태그를 *이 음식의 태그*로 교체 → 먹거리 일기에서
            # [태그]🍽[음식] 짝이 페르소나와 일치 (예: [얼큰한,국물있는]🍽짬뽕).
            # seed_demo 가 박은 무관한 태그([달달한]🍽짬뽕 같은) 부정합 제거.
            conn.execute("DELETE FROM UserTagSelection WHERE session_id = ?", (sess,))
            for tid in _food_tag_ids(conn, fid, 3):
                conn.execute(
                    "INSERT INTO UserTagSelection(session_id, tag_id) VALUES (?, ?)",
                    (sess, tid),
                )
            inserted.append(name)

        print(f"  ✅ {label} (user {uid}): 로그 {before}→{len(inserted)}개 final (최근 세션 분산)  시그니처={inserted}")


def main() -> None:
    print(f"DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        trim(conn)
        conn.commit()
    finally:
        conn.close()
    print("완료. (재실행 안전 — 매번 같은 시그니처로 재설정)")


if __name__ == "__main__":
    main()
