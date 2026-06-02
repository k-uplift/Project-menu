"""비밀번호 해시 유틸 (표준 라이브러리만 사용).

평문 비밀번호는 절대 저장하지 않는다. 회원가입 시 hash_password() 로
해시 문자열을 만들어 User.password_hash 에 저장하고, 로그인 시
verify_password() 로 입력값과 저장된 해시를 비교한다.

알고리즘: PBKDF2-HMAC-SHA256 (hashlib 내장)
저장 포맷 (Django 호환 스타일, self-describing):
    pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
  - iterations 를 포맷에 박아두므로, 나중에 반복 횟수를 올려도
    기존 해시는 자기 자신의 횟수로 검증된다(점진적 업그레이드 가능).

사용 예:
    from src.data.database.password import hash_password, verify_password
    stored = hash_password("mypw1234")          # 회원가입: DB 에 저장
    verify_password("mypw1234", stored)  # True  # 로그인: 입력값 검증
    verify_password("wrong", stored)     # False
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 390_000          # OWASP 권장(SHA256) 수준
SALT_BYTES = 16
HASH_NAME = "sha256"


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    """평문 비밀번호 → 저장용 해시 문자열."""
    if not password:
        raise ValueError("비밀번호가 비어 있습니다.")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(HASH_NAME, password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """입력 평문이 저장된 해시와 일치하는지 (상수 시간 비교)."""
    if not password or not stored:
        return False
    try:
        algorithm, iter_str, salt_hex, hash_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac(HASH_NAME, password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)
