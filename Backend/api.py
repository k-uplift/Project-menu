"""me:nu 추천 HTTP wrapper.

src/llm/match.py의 recommend_foods / recommend_stores_for_kind를
HTTP로 노출. 프론트(React Native + Expo)가 mock 대신 이 API를 호출.

실행:
    cd Backend
    uvicorn api:app --reload --host 0.0.0.0 --port 8000

엔드포인트:
    GET /                              헬스체크
    GET /foods?q=...                   자연어 → 음식 종류 추천
    GET /restaurants?q=...&kind=...    선택 종류 → 식당 추천

응답은 match.py가 만든 프론트 계약 dict 그대로.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.llm.match import recommend_foods, recommend_stores_for_kind

app = FastAPI(title="me:nu recommendation API")

# 개발용 — 모든 origin 허용. 배포 시 Expo/도메인만으로 좁히기.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
def health():
    return {"status": "ok", "service": "menu-recommendation"}


@app.get("/foods")
def foods(q: str, top_k: int = 10):
    """자연어 쿼리 → 음식 종류 추천 (1차)."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is empty")
    return recommend_foods(q, top_k=top_k)


@app.get("/restaurants")
def restaurants(q: str, kind: str, top_k: int = 10):
    """선택한 음식 종류 → 그 종류의 식당 추천 (2차).

    q는 1차에서 쓴 쿼리 그대로 — 사용자 취향이 식당 점수에 반영되도록.
    """
    if not q.strip() or not kind.strip():
        raise HTTPException(status_code=400, detail="q and kind required")
    return recommend_stores_for_kind(q, kind, top_k=top_k)
