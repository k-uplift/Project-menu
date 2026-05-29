"""me:nu 추천 HTTP wrapper.

src/llm/match.py의 recommend_foods / recommend_stores_for_kind를
HTTP로 노출. 프론트(React Native + Expo)가 mock 대신 이 API를 호출.

실행:
    cd Backend
    uvicorn api:app --reload --host 0.0.0.0 --port 8000

엔드포인트:
    GET /                                  헬스체크
    GET /foods?q=...                       자연어 → 음식 종류 추천
    GET /restaurants?q=...&kind=...        선택 종류 → 식당 추천
    GET /restaurants/{store_id}/menus      그 식당의 전체 메뉴 (RestaurantDetail용)

응답은 match.py가 만든 프론트 계약 dict 그대로.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.llm.match import (
    load_menu_tags,
    recommend_foods,
    recommend_stores_for_kind,
)

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


@app.get("/restaurants/{store_id}/menus")
def store_menus(store_id: int):
    """한 식당의 *전체* 메뉴 — RestaurantDetail 화면용.

    /restaurants 응답의 menuItems는 *선택한 kind에 매칭된 메뉴*만 담겨 있어
    사용자가 식당 상세를 열면 "메뉴가 적다"는 인상을 받음. 이 엔드포인트는
    그 식당의 모든 메뉴(태그·가격 포함)를 반환해, 화면이 *추천 메뉴 강조 +
    전체 메뉴 목록* 두 섹션으로 구성 가능하게 한다.

    응답: {"storeId", "menus": [{name, price, tags, kind}, ...]}
    """
    rows = [r for r in load_menu_tags() if r.store_id == store_id]
    return {
        "storeId": store_id,
        "menus": [
            {
                "name": r.menu_name,
                "price": r.price,
                "tags": r.tags,
                "kind": r.kind,
            }
            for r in rows
        ],
    }
