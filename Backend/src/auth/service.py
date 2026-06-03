"""회원가입/로그인 순수 로직 (웹프레임워크 비의존).

기존 자산 재사용:
  - password.hash_password / verify_password : 비밀번호 해시·검증(PBKDF2)
  - schema.connect / init_db                : recommend.db 연결
  - tokens.issue_token                      : 로그인 성공 시 무상태 토큰 발급

라우터(routes.py)·CLI·테스트 어디서든 호출 가능하도록 sqlite 만 직접 다룬다.
AuthError(code, message) 로 실패 사유를 구분해 호출측이 HTTP 상태로 매핑한다.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from src.data.database.password import hash_password, verify_password
from src.data.database.schema import DB_PATH, connect, init_db
from src.auth.tokens import issue_token

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8


class AuthError(Exception):
    """인증 실패. code 는 호출측(HTTP)에서 상태코드로 매핑."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _public_user(row: sqlite3.Row | tuple) -> dict:
    """비밀번호 해시를 제외한 외부 노출용 유저 정보."""
    return {"user_id": row[0], "email": row[1]}


def signup(email: str, password: str, *, db_path: Path = DB_PATH) -> dict:
    """회원가입. 성공 시 {user, token}. 실패 시 AuthError.

    - email 형식/중복 검사, password 최소 길이 검사
    - password 는 해시만 저장(평문 저장 금지)
    """
    email = _normalize_email(email)
    if not _EMAIL_RE.match(email):
        raise AuthError("invalid_email", "이메일 형식이 올바르지 않습니다.")
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise AuthError("weak_password", f"비밀번호는 최소 {MIN_PASSWORD_LEN}자 이상이어야 합니다.")

    init_db(db_path)
    conn = connect(db_path)
    try:
        exists = conn.execute("SELECT 1 FROM User WHERE email = ?", (email,)).fetchone()
        if exists:
            raise AuthError("email_taken", "이미 가입된 이메일입니다.")
        cur = conn.execute(
            "INSERT INTO User(email, password_hash) VALUES (?, ?)",
            (email, hash_password(password)),
        )
        conn.commit()
        user_id = cur.lastrowid
    finally:
        conn.close()

    user = {"user_id": user_id, "email": email}
    return {"user": user, "token": issue_token(user_id, email)}


def login(email: str, password: str, *, db_path: Path = DB_PATH) -> dict:
    """로그인. 성공 시 {user, token}. 실패 시 AuthError('invalid_credentials').

    이메일 존재 여부와 비밀번호 오류를 구분하지 않는다(계정 열거 공격 방지).
    """
    email = _normalize_email(email)
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT user_id, email, password_hash FROM User WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if row is None or not verify_password(password, row[2]):
        raise AuthError("invalid_credentials", "이메일 또는 비밀번호가 올바르지 않습니다.")

    user = {"user_id": row[0], "email": row[1]}
    return {"user": user, "token": issue_token(row[0], row[1])}


def get_user(user_id: int, *, db_path: Path = DB_PATH) -> dict | None:
    """user_id 로 외부 노출용 유저 정보 조회(없으면 None)."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT user_id, email FROM User WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    return _public_user(row) if row else None
