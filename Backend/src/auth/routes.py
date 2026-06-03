"""FastAPI 인증 라우터.

엔드포인트(prefix /auth):
  POST /auth/signup  {email, password}        → 201 {user, token}
  POST /auth/login   {email, password}        → 200 {user, token}
  GET  /auth/me      Authorization: Bearer …  → 200 {user}

추후 통합 서버(api.py)로 흡수할 때:  app.include_router(auth.routes.router)
한 줄이면 되도록 라우터를 독립 모듈로 둔다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.auth.service import AuthError, get_user, login, signup
from src.auth.tokens import verify_token

router = APIRouter(prefix="/auth", tags=["auth"])

# 서비스 계층 에러코드 → HTTP 상태코드 매핑
_STATUS = {
    "invalid_email": status.HTTP_400_BAD_REQUEST,
    "weak_password": status.HTTP_400_BAD_REQUEST,
    "email_taken": status.HTTP_409_CONFLICT,
    "invalid_credentials": status.HTTP_401_UNAUTHORIZED,
}


class Credentials(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _raise(err: AuthError) -> None:
    raise HTTPException(
        status_code=_STATUS.get(err.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": err.code, "message": err.message},
    )


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """Authorization: Bearer <token> 헤더를 검증해 현재 유저 반환."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="인증 토큰이 없습니다.")
    payload = verify_token(authorization.split(" ", 1)[1].strip())
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="토큰이 유효하지 않거나 만료되었습니다.")
    user = get_user(payload["uid"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="유저를 찾을 수 없습니다.")
    return user


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup_route(body: Credentials) -> dict:
    try:
        return signup(body.email, body.password)
    except AuthError as err:
        _raise(err)


@router.post("/login")
def login_route(body: Credentials) -> dict:
    try:
        return login(body.email, body.password)
    except AuthError as err:
        _raise(err)


@router.get("/me")
def me_route(user: dict = Depends(current_user)) -> dict:
    return {"user": user}
