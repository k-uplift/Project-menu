"""me:nu 추천 HTTP wrapper.

두 추천 채널을 동시 노출:
  - /foods    = src/llm/match.py — 363 kind 풀 + IDF + food_kw + 사이드 디부스트.
                평가셋 lenient 97.2% 검증된 콘텐츠 매칭. *기본 추천 탭*.
  - /foods_cf = cf_module Tab2 (사용자 기반 CF, recommend.db 기반) —
                "나와 취향이 비슷한 사용자들이 고른 메뉴". *개인화 추천 탭*.

cf_module 의 Tab1 (세션 기반)은 *호출 X*. recommend_foods 가 더 풍부한 풀과
다듬어진 알고리즘으로 같은 자리를 더 잘 채움. cf_module 코드 자체는 보존 —
adapter.py 가 recommend.db 를 본 채로 살아있어 Tab2 가 그대로 동작.

실행:
    cd Backend
    uvicorn api:app --reload --host 0.0.0.0 --port 8000

엔드포인트:
    GET  /                                 헬스체크
    GET  /extract?q=...                    자연어 → 시드 14 태그 추출 (검수용)
    GET  /foods?q=...&user_id=1            자연어 → 콘텐츠 매칭 추천 (match.py)
    GET  /foods_cf?q=...&user_id=1         자연어 → 개인화 CF 추천 (cf_module Tab2)
    GET  /restaurants?q=...&kind=...       선택 종류 → 식당 추천
    GET  /restaurants/{store_id}/menus     그 식당의 전체 메뉴 (RestaurantDetail용)
    POST /events                           클릭/최종선택 이벤트 기록 (DB 동적 wiring)

DB 동적 wiring (묶음 X, 6/1):
  /foods·/foods_cf 호출 시 RecommendationSession INSERT + UserTagSelection INSERT.
  응답에 session_id 포함 → 프론트가 보관해 후속 /events 호출 시 같이 보냄.
  POST /events에서 UserInteractionLog INSERT + UserFoodTagWeight UPSERT.
"""

# api.py는 Backend/ 안에 있지만 cf_module/은 프로젝트 루트에 있다 — sys.path 추가.
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.data.database.sessions import (
    create_session,
    ensure_demo_user,
    log_event,
    save_tag_selections,
)
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
# POST 추가했으니 methods도 확장.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _bootstrap():
    """User(1) 데모 계정 보장. FK 제약을 위해 1회 보장."""
    ensure_demo_user(user_id=1)


@app.get("/")
def health():
    return {"status": "ok", "service": "menu-recommendation"}


def _open_session_and_save_tags(user_id: int, tag_names: list[str]) -> int:
    """추천 호출의 공통 진입 — 세션 만들고 추출 태그 저장. session_id 반환."""
    session_id = create_session(user_id=user_id)
    if tag_names:
        save_tag_selections(session_id, tag_names)
    return session_id


@app.get("/extract")
def extract(q: str):
    """자연어 → 키워드 추출만 (가벼움, 검수 화면용).

    홈 입력을 키워드 검수 페이지로 넘기기 전에 호출. /foods는 추천까지
    같이 만드는 무거운 호출이라 *키워드만* 보여줄 단계엔 과함.

    응답 keywords: tags(시드) + food_keywords(카테고리·식재료) 합본.
      - 시드는 confidence 0.9 (정확)
      - food_keywords는 confidence 0.7 (보조 — Claude open vocab)
      - exclude는 별도 필드로 노출 (UI 부정 표시 옵션)
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is empty")
    e = extract_tags(q)

    # 프론트 Keyword 구조에 맞춰 변환 — *시드만* 노출.
    # food_keywords는 *내부 메뉴명 매칭 보조* 채널이라 사용자에게 직접 보여주면
    # 키워드 검수 단계 = 추천 미리보기 효과 → 단계 분리 의미 약화.
    # 추천 단계(/foods)는 응답의 foodKeywords 필드를 그대로 받아 *내부 매칭에 사용*.
    keywords = []
    for i, t in enumerate(e.tags or []):
        keywords.append({"id": f"kw-tag-{i}", "label": t, "confidence": 0.9, "source": "llm"})

    return {
        "originalText": q,
        "keywords": keywords,
        "tags": e.tags or [],
        "foodKeywords": e.food_keywords or [],
        "excludeTags": e.exclude_tags or [],
        "excludeFoodKeywords": e.exclude_food_keywords or [],
    }


def _cf_results_to_kinds(results, rep_tags) -> list[dict]:
    """cf_module RecommendationResult[] → 프론트 카드 계약(kinds[]) 변환.

    /foods·/foods_cf 양쪽에서 동일 패턴이라 헬퍼로 추출.
    tags 는 *rep_tags 캐시* (kind 자체 대표 태그 top 4) 우선, 폴백으로 matched_tags.
    score 0~100 매핑은 시연용 (raw float → 정수). cf_module Tab1 score 범위는
    대체로 0~10, Tab2 는 0~5 정도 → ×5+50 으로 펴면 50~100 사이로 안착.
    """
    kinds = []
    for r in results:
        kinds.append({
            "id": KIND_TO_FOOD_ID.get(r.kind_name, f"food-{r.kind_name}"),
            "name": r.kind_name,
            "emoji": None,
            "imageUrl": None,
            "tags": rep_tags.get(r.kind_name, list(r.matched_tags)),
            "score": min(100, 50 + int(r.score * 5)),
            "reason": {
                "matchedKeywords": list(r.matched_tags),
                "matchedFoodKeywords": [],
                "cfScore": round(r.score, 2),
                "cfDescription": r.reason,
                "contextNote": None,
            },
        })
    return kinds


@app.get("/foods")
def foods(q: str, top_k: int = 10, user_id: int = 1):
    """자연어 쿼리 → 기본 추천 (콘텐츠 매칭, match.py).

    363 kind vocab + IDF 가중 + food_keywords 채널 + 사이드 디부스트.
    평가셋 lenient 97.2% 검증된 알고리즘. 추천 결과는 *DB 행동 데이터와 무관* —
    정적 menu_tags.jsonl + menu_kinds.jsonl + details.db.stores 만 본다.

    DB 동적 wiring (Session/Tag/Log/Weight) 은 그대로. 검색마다 RecommendationSession
    + UserTagSelection INSERT — 후속 CF 신호로 흘러간다.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is empty")
    result = recommend_foods(q, top_k=top_k)
    session_id = _open_session_and_save_tags(user_id, result.get("keywords", []))
    result["sessionId"] = session_id
    result["userId"] = user_id
    return result


@app.get("/foods_cf")
def foods_cf(q: str, user_id: int = 1, top_k: int = 10):
    """개인화 추천 (cf_module Tab2 personalized, 사용자 기반 CF).

    "나와 *행동 윤곽이 닮은 사용자들*이 고른 메뉴". user_id 의 final_select 한 kind 는
    재추천에서 제외 (이미 먹어본 거). click 만 한 kind 는 후보로 남김 (관심 단계).

    응답 모양은 /foods 와 동일 (kinds[]·sessionId·userId).
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is empty")

    extracted = extract_tags(q)
    cf_response = cf_recommend(extracted.tags, user_id=user_id, top_k=top_k)

    rep_tags = _get_kind_rep_tags()
    kinds = _cf_results_to_kinds(cf_response.tab2_results, rep_tags)

    session_id = _open_session_and_save_tags(user_id, extracted.tags)
    return {
        "query": q,
        "userId": user_id,
        "sessionId": session_id,
        "keywords": extracted.tags,
        "kinds": kinds,
        "emptyReason": cf_response.tab2_empty_reason,
    }


# 배민 URL 매핑 — 시연용 식당 N개. 키 = stores.name. 값 = 배민 deep link.
# 값이 빈 문자열이면 프론트가 검색 URL로 fallback.
_BAEMIN_URLS_PATH = Path(__file__).parent / "data" / "baemin_urls.json"
_BAEMIN_URLS_CACHE: dict[str, str] | None = None


def _load_baemin_urls() -> dict[str, str]:
    global _BAEMIN_URLS_CACHE
    if _BAEMIN_URLS_CACHE is None:
        try:
            raw = json.loads(_BAEMIN_URLS_PATH.read_text(encoding="utf-8"))
            # '_comment' 같은 키는 무시. 빈 값도 그대로 — 프론트에서 분기.
            _BAEMIN_URLS_CACHE = {k: v for k, v in raw.items() if not k.startswith("_") and v}
        except FileNotFoundError:
            _BAEMIN_URLS_CACHE = {}
    return _BAEMIN_URLS_CACHE


@app.get("/restaurants")
def restaurants(q: str, kind: str, top_k: int = 10):
    """선택한 음식 종류 → 그 종류의 식당 추천 (2차).

    q는 1차에서 쓴 쿼리 그대로 — 사용자 취향이 식당 점수에 반영되도록.
    응답 stores[] 각 item에 baeminUrl 주입 (시연용 매핑에 있는 식당만).
    """
    if not q.strip() or not kind.strip():
        raise HTTPException(status_code=400, detail="q and kind required")
    result = recommend_stores_for_kind(q, kind, top_k=top_k)
    baemin_urls = _load_baemin_urls()
    for store in result.get("stores", []):
        url = baemin_urls.get(store.get("name"))
        if url:
            store["baeminUrl"] = url
    return result


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


# ── POST /events — 클릭/최종선택 이벤트 기록 ──────────────────────────────────
class EventBody(BaseModel):
    """프론트 behaviorTrackingService가 보내는 이벤트 페이로드.

    action_type: 'click' (food_card_click, +1점) / 'final_select' (navigate·delivery, +2점)
    food_name: kind 이름 (예: '김치찌개'). Food 테이블에 없으면 NULL 기록만, 가중치 적용 X.
    session_id: /foods·/foods_cf 응답에서 받은 값. None이면 가중치 적용 X (로그만).
    """
    user_id: int = 1
    session_id: int | None = None
    food_name: str
    action_type: str


@app.post("/events")
def post_event(body: EventBody):
    try:
        result = log_event(
            user_id=body.user_id,
            session_id=body.session_id,
            food_name=body.food_name,
            action_type=body.action_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, **result}
