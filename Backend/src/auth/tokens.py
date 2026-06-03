"""무상태(stateless) 인증 토큰.

세션 테이블 없이, 서명된 토큰 자체에 (user_id, email, 만료시각) 을 담는다.
서버는 비밀키로 HMAC-SHA256 서명만 검증하므로 DB 조회/스키마 변경이 없다.

토큰 포맷 (자기서술적, URL-safe):
    base64url(payload_json) + "." + base64url(hmac_sha256(payload))

  - 비밀키: 환경변수 AUTH_SECRET (미설정 시 개발용 기본값 — 운영 배포 전 반드시 설정).
  - 만료(exp): 발급 시각 + TTL(기본 7일). 검증 시 현재 시각과 비교.

표준 라이브러리만 사용한다(hashlib/hmac/base64/json).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

# ⚠️ 운영 배포 전 AUTH_SECRET 환경변수를 반드시 설정할 것. 기본값은 개발 전용.
_SECRET = os.environ.get("AUTH_SECRET", "dev-insecure-secret-change-me").encode("utf-8")
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 7  # 7일


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str) -> str:
    digest = hmac.new(_SECRET, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def issue_token(
    user_id: int,
    email: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """(user_id, email) 에 대한 서명 토큰 발급."""
    issued = int(now if now is not None else time.time())
    payload = {"uid": user_id, "email": email, "iat": issued, "exp": issued + ttl_seconds}
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_token(token: str, *, now: float | None = None) -> dict | None:
    """유효하면 payload(dict) 반환, 위조/만료/형식오류면 None."""
    if not token or "." not in token:
        return None
    payload_b64, signature = token.rsplit(".", 1)
    # 상수 시간 비교로 서명 검증
    if not hmac.compare_digest(signature, _sign(payload_b64)):
        return None
    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    current = now if now is not None else time.time()
    if not isinstance(payload.get("exp"), (int, float)) or payload["exp"] < current:
        return None
    return payload
