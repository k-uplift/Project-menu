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
        first_session = sessions[0]

        qmarks = ",".join("?" for _ in sessions)
        before = conn.execute(
            f"SELECT COUNT(*) FROM UserInteractionLog WHERE session_id IN ({qmarks})",
            sessions,
        ).fetchone()[0]

        # 1) 이 계정의 모든 행동 로그 삭제
        conn.execute(
            f"DELETE FROM UserInteractionLog WHERE session_id IN ({qmarks})", sessions
        )
        # 2) 시그니처 kind 를 final_select 로 첫 세션에 INSERT
        inserted = []
        for name in sig_names:
            fid = _food_id(conn, name)
            if fid is None:
                print(f"  ⚠️  '{name}' Food 테이블에 없음 — 건너뜀")
                continue
            conn.execute(
                "INSERT INTO UserInteractionLog(session_id, food_id, action_type, created_at) "
                "VALUES (?, ?, 'final_select', datetime('now'))",
                (first_session, fid),
            )
            inserted.append(name)

        print(f"  ✅ {label} (user {uid}): 로그 {before}→{len(inserted)}개 final  시그니처={inserted}")


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
