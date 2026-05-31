"""추천 세션·이벤트 DB 헬퍼.

api.py가 추천 호출/이벤트 수신 시 recommend.db에 흔적을 남기는 책임을 모음.
정적 데이터(Tag/Food)는 read-only로 참조하고, 동적 데이터(Session/Selection/Log/Weight)는
INSERT/UPSERT를 수행한다.

연결 정책: 함수마다 새로 connect() → try/finally close. PRAGMA foreign_keys = ON 자동.

가중치 정책 (CLAUDE.md 5/29 결정):
    food_card_click       → 'click'         (+1점)
    navigate_click        → 'final_select'  (+2점)
    delivery_click        → 'final_select'  (+2점)
"""
from __future__ import annotations

import sqlite3
from typing import Iterable

from src.data.database.schema import connect

WEIGHTS = {"click": 1, "final_select": 2}
ALLOWED_ACTIONS = set(WEIGHTS.keys())


def ensure_demo_user(user_id: int = 1) -> None:
    """User(user_id=1)이 없으면 데모 계정 생성. FastAPI startup에서 1회 호출.

    UserFoodTagWeight의 PK가 (user_id, food_id, tag_id)라 user_id가 *실제 행*으로
    존재해야 FK 위반 없이 INSERT 가능. 회원가입 화면 도입 전엔 모든 시연이 user_id=1.
    """
    conn = connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO User (user_id, email) VALUES (?, ?)",
            (user_id, f"demo{user_id}@menu.local"),
        )
        conn.commit()
    finally:
        conn.close()


def create_session(user_id: int = 1) -> int:
    """추천 세션 1행 INSERT, session_id 반환."""
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO RecommendationSession (user_id) VALUES (?)",
            (user_id,),
        )
        session_id = cur.lastrowid
        conn.commit()
        return session_id
    finally:
        conn.close()


def save_tag_selections(session_id: int, tag_names: Iterable[str]) -> int:
    """세션에 *추출된 시드 태그* N개 INSERT. Tag 테이블에 없는 토큰(=시드 14 외)은 무시."""
    conn = connect()
    try:
        rows = conn.execute("SELECT tag_name, tag_id FROM Tag").fetchall()
        tag_map = {name: tid for name, tid in rows}
        pairs = [(session_id, tag_map[t]) for t in tag_names if t in tag_map]
        if pairs:
            conn.executemany(
                "INSERT INTO UserTagSelection (session_id, tag_id) VALUES (?, ?)",
                pairs,
            )
            conn.commit()
        return len(pairs)
    finally:
        conn.close()


def log_event(
    *,
    user_id: int,
    session_id: int | None,
    food_name: str,
    action_type: str,
) -> dict:
    """클릭/최종선택 이벤트 1건 처리.

    1. food_name → food_id 조회 (Food 테이블에 없으면 NULL로 INSERT만, weight 적용 안 함)
    2. UserInteractionLog INSERT
    3. session_id가 있으면 그 세션의 UserTagSelection 조회해서
       (user, food, tag) 각 조합마다 UserFoodTagWeight UPSERT += 가중치

    Returns: {"log_id", "food_id", "tags_applied", "weight"}
    """
    if action_type not in ALLOWED_ACTIONS:
        raise ValueError(f"action_type must be one of {ALLOWED_ACTIONS}, got {action_type!r}")
    weight = WEIGHTS[action_type]

    conn = connect()
    try:
        # food_name → food_id (없으면 NULL로 로깅만 — '기타' 같은 안전망 kind도 OK)
        food_row = conn.execute(
            "SELECT food_id FROM Food WHERE food_name = ? LIMIT 1",
            (food_name,),
        ).fetchone()
        food_id = food_row[0] if food_row else None

        cur = conn.execute(
            "INSERT INTO UserInteractionLog (session_id, food_id, action_type) VALUES (?, ?, ?)",
            (session_id, food_id, action_type),
        )
        log_id = cur.lastrowid

        tags_applied = 0
        if session_id is not None and food_id is not None:
            tag_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT tag_id FROM UserTagSelection WHERE session_id = ?",
                    (session_id,),
                ).fetchall()
            ]
            # 같은 (user, food, tag) 조합이면 total_weight 누적. SQLite UPSERT 구문.
            for tag_id in tag_ids:
                conn.execute(
                    """
                    INSERT INTO UserFoodTagWeight (user_id, food_id, tag_id, total_weight)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, food_id, tag_id)
                    DO UPDATE SET total_weight = total_weight + excluded.total_weight
                    """,
                    (user_id, food_id, tag_id, weight),
                )
                tags_applied += 1

        conn.commit()
        return {
            "log_id": log_id,
            "food_id": food_id,
            "tags_applied": tags_applied,
            "weight": weight,
        }
    finally:
        conn.close()
