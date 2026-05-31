"""me:nu 추천 HTTP wrapper.

src/llm/match.py(태그 매칭)와 cf_module(세션 기반 CF)을 HTTP로 노출.
프론트(React Native + Expo)가 mock 대신 이 API를 호출.

실행:
    cd Backend
    uvicorn api:app --reload --host 0.0.0.0 --port 8000

엔드포인트:
    GET /                                  헬스체크
    GET /foods?q=...                       자연어 → 음식 종류 추천 (태그 매칭, 우리 match.py)
    GET /foods_cf?q=...&user_id=1          자연어 → 세션 기반 CF 추천 (cf_module, 양혜원)
    GET /restaurants?q=...&kind=...        선택 종류 → 식당 추천
    GET /restaurants/{store_id}/menus      그 식당의 전체 메뉴 (RestaurantDetail용)

응답은 match.py가 만든 프론트 계약 dict 그대로.
"""

# api.py는 Backend/ 안에 있지만 cf_module/은 프로젝트 루트에 있다 — sys.path 추가.
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.llm.extract import extract_tags
from src.llm.kinds import KIND_TO_FOOD_ID
from src.llm.match import (
    _get_kind_rep_tags,
    load_menu_tags,
    recommend_foods,
    recommend_stores_for_kind,
)

from cf_module.core.recommend import recommend as cf_recommend

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


@app.get("/foods_cf")
def foods_cf(q: str, user_id: int = 1, top_k: int = 10):
    """세션 기반 CF 추천 (cf_module).

    우리 extract.py로 입력 태그를 뽑은 뒤 cf_module.recommend로 tab2(CF)만 사용.
    cf_module의 tab1(태그 매칭)은 합성 50 kind 한정이라 사용 X — 메인 /foods가 우리
    match.py로 363 kind 풀 전체에서 더 풍부하게 잡는다.

    응답 모양은 /foods와 동일 (kinds[] 배열) — 프론트가 같은 카드 컴포넌트로 렌더.
    user_id 기본 1: 익명 사용자 = 합성 페르소나 1번. 실 사용자 도입 전 시연용.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is empty")

    extracted = extract_tags(q)
    cf_response = cf_recommend(extracted.tags, user_id=user_id, top_k=top_k)

    rep_tags = _get_kind_rep_tags()
    kinds = []
    for r in cf_response.tab2_results:
        kinds.append({
            "id": KIND_TO_FOOD_ID.get(r.kind_name, f"food-{r.kind_name}"),
            "name": r.kind_name,
            "emoji": None,
            "imageUrl": None,
            "tags": rep_tags.get(r.kind_name, list(r.matched_tags)),
            # cf_module score는 raw float (~0~수십). 시연용으로 50~100 사이로 매핑.
            "score": min(100, 50 + int(r.score * 5)),
            "reason": {
                "matchedKeywords": list(r.matched_tags),
                "matchedFoodKeywords": [],
                "cfScore": round(r.score, 2),
                "cfDescription": r.reason,
                "contextNote": None,
            },
        })
    return {
        "query": q,
        "userId": user_id,
        "keywords": extracted.tags,
        "kinds": kinds,
    }


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
