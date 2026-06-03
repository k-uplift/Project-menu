"""인증 엔드포인트 단독 실행용 FastAPI 앱 (검증/개발용).

llm-tag 의 통합 서버(api.py)와 충돌하지 않도록 파일명을 분리했다.
추후 통합 시에는 api.py 에서 `from src.auth.routes import router` 후
`app.include_router(router)` 한 줄로 흡수하면 된다.

📄 병합 절차·충돌 해소·검증 체크리스트: docs/MERGE_auth_to_llm-tag.md (병합 전 필독)

실행 (Backend/ 디렉터리에서):
    uvicorn auth_app:app --reload --port 8000

검증 예:
    curl -X POST localhost:8000/auth/login \
         -H "Content-Type: application/json" \
         -d '{"email":"t1_u1@demo","password":"demo1234"}'
"""
from __future__ import annotations

from fastapi import FastAPI

from src.auth.routes import router

app = FastAPI(title="menu-auth", description="로그인/회원가입 엔드포인트")
app.include_router(router)


@app.get("/")
def health() -> dict:
    return {"status": "ok", "service": "menu-auth"}
