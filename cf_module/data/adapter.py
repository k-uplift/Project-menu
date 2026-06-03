"""recommend.db → cf_module 데이터 모델 어댑터.

synthetic.get_synthetic_dataset() 과 같은 시그니처를 제공해서
cf_module/core/recommend.py 의 import 한 줄만 바꾸면 실 DB 기반으로 동작한다.

Food            → FoodKind
FoodTag         → FoodKind.tags
RecommendationSession ⨝ UserTagSelection ⨝ UserInteractionLog → SearchSession

매핑 약속:
  - kind_id   = Food.food_id
  - session_id = RecommendationSession.session_id
  - user_id   = User.user_id
  - input_tags = 그 세션의 UserTagSelection 태그 이름들 (시드 14개 안)
  - actions   = 그 세션의 UserInteractionLog (food_id → kind_id, action_type 그대로)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from cf_module.models import FoodKind, MenuAction, SearchSession


# Project-menu/cf_module/data/adapter.py → Project-menu/Backend/db/recommend.db
_DB_PATH = Path(__file__).resolve().parents[2] / "Backend" / "db" / "recommend.db"


def _load_kinds(conn: sqlite3.Connection) -> list[FoodKind]:
    """Food + FoodTag → FoodKind 리스트.

    FoodTag 가 0행인 음식도 포함한다 (tags=[]). 그래야 추천 후보 풀이
    Food 테이블 전체와 일치한다. 단 Tab1/Tab2 매칭에는 tags 가 있어야
    잡히므로 빈 tags 의 음식은 자연스레 후보에서 빠진다.
    """
    food_tags: dict[int, list[str]] = {}
    for food_id, tag_name in conn.execute(
        "SELECT ft.food_id, t.tag_name FROM FoodTag ft JOIN Tag t ON t.tag_id = ft.tag_id"
    ):
        food_tags.setdefault(food_id, []).append(tag_name)

    kinds: list[FoodKind] = []
    for food_id, food_name in conn.execute("SELECT food_id, food_name FROM Food ORDER BY food_id"):
        kinds.append(FoodKind(kind_id=food_id, name=food_name, tags=food_tags.get(food_id, [])))
    return kinds


def _load_sessions(conn: sqlite3.Connection) -> list[SearchSession]:
    """RecommendationSession + UserTagSelection + UserInteractionLog → SearchSession 리스트.

    세션 한 개당 한 행. input_tags 와 actions 를 각각 조인해서 채운다.
    UserTagSelection 이 비어 있는 세션은 input_tags=[] 로 들어가는데, 그 세션은
    Tab1 의 Jaccard 분자가 0 이라 점수 기여 없음.
    """
    session_tags: dict[int, list[str]] = {}
    for session_id, tag_name in conn.execute(
        "SELECT uts.session_id, t.tag_name "
        "FROM UserTagSelection uts JOIN Tag t ON t.tag_id = uts.tag_id"
    ):
        session_tags.setdefault(session_id, []).append(tag_name)

    session_actions: dict[int, list[MenuAction]] = {}
    for session_id, food_id, action_type in conn.execute(
        "SELECT session_id, food_id, action_type FROM UserInteractionLog "
        "WHERE action_type IN ('click', 'final_select')"
    ):
        session_actions.setdefault(session_id, []).append(
            MenuAction(kind_id=food_id, action_type=action_type)
        )

    sessions: list[SearchSession] = []
    for session_id, user_id, created_at in conn.execute(
        "SELECT session_id, user_id, created_at FROM RecommendationSession ORDER BY session_id"
    ):
        sessions.append(
            SearchSession(
                session_id=session_id,
                user_id=user_id,
                input_tags=session_tags.get(session_id, []),
                actions=session_actions.get(session_id, []),
                timestamp=created_at or "",
            )
        )
    return sessions


def get_db_dataset(db_path: Path = _DB_PATH) -> tuple[list[FoodKind], list[SearchSession]]:
    """synthetic.get_synthetic_dataset() 과 같은 시그니처.

    read-only 모드로 열어 cf_module 가 DB 를 수정하지 않게 한다.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        kinds = _load_kinds(conn)
        sessions = _load_sessions(conn)
        return kinds, sessions
    finally:
        conn.close()


if __name__ == "__main__":
    kinds, sessions = get_db_dataset()
    print(f"kinds: {len(kinds)}개")
    print(f"sessions: {len(sessions)}개")
    users = {s.user_id for s in sessions}
    print(f"users: {len(users)}명")
    with_tags = sum(1 for s in sessions if s.input_tags)
    print(f"sessions with input_tags: {with_tags}")
    with_actions = sum(1 for s in sessions if s.actions)
    print(f"sessions with actions: {with_actions}")
    sample = next((k for k in kinds if k.tags), None)
    if sample:
        print(f"예시 kind: {sample.name} {sample.tags}")
    sample_session = next((s for s in sessions if s.input_tags and s.actions), None)
    if sample_session:
        print(f"예시 session: user={sample_session.user_id} "
              f"tags={sample_session.input_tags} "
              f"actions={[(a.kind_id, a.action_type) for a in sample_session.actions]}")
