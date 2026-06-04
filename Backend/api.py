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
from src.data.database.schema import connect as _connect_recommend_db
from src.llm.extract import extract_tags
from src.llm.kinds import KIND_TO_FOOD_ID, KIND_TO_CATEGORY


# ── 카테고리 친근 라벨 ───────────────────────────────────────────────────────
# kinds.py 의 raw 카테고리 ('한식국물탕') 를 카드에 보일 친근 표현 ('한식 국물요리')
# 으로 변환. 기본 탭 카드의 추천 근거 문장에 사용.
_CATEGORY_LABELS: dict[str, str] = {
    "한식국물탕": "한식 국물요리",
    "한식고기":   "한식 고기요리",
    "한식면밥":   "한식 면·밥",
    "한식조림찜": "한식 조림·찜",
    "일식":       "일식",
    "중식":       "중식",
    "양식":       "양식",
    "디저트":     "디저트",
    "치킨":       "치킨",
    "분식":       "분식",
    "도시락":     "도시락",
}


def _build_kind_reason_desc(
    kind_name: str,
    n_stores: int,
    matched_count: int,
    total_keywords: int,
) -> str:
    """기본 탭 카드 추천 근거. '검색 키워드 모두 일치·12개 식당이 판매' 형태.

    매칭의 *강도* (검색 의도와 얼마나 일치) + *데이터 신뢰* (식당 검증) 결합.
    CF 탭의 'Charlie 등 N명이 선택' 과 문장 구조 매치.
    """
    parts: list[str] = []
    if total_keywords > 0:
        if matched_count >= total_keywords:
            parts.append("검색 키워드 모두 일치")
        elif matched_count > 0:
            parts.append(f"검색 키워드 {matched_count}/{total_keywords} 일치")
    if n_stores > 0:
        parts.append(f"{n_stores}개 식당이 판매")
    return " · ".join(parts) if parts else ""
from src.llm.match import (
    _get_kind_rep_tags,
    load_menu_tags,
    recommend_foods,
    recommend_foods_by_tags,
    recommend_stores_for_kind,
)
from src.auth.routes import router as auth_router

from cf_module.core.recommend import (
    recommend as cf_recommend,
    _find_similar_users as _cf_find_similar_users,
    _get_user_kind_max_weight as _cf_user_kind_weight,
)

# ── CF 카드 supporters 이름 매핑 ─────────────────────────────────────────────
# 시연용 3명 (Alice·Bob·Charlie) 만 친근한 이름. 나머지 77명은 페르소나 라벨.
# seed_demo 의 TYPES 순서로 user_id 1~10=T1, 11~20=T2, ... 81~10=T8.
_USER_DISPLAY_NAMES: dict[int, str] = {
    1:  "Alice",
    2:  "Charlie",
    41: "Bob",
}
_PERSONA_LABELS = [
    "매운국물파", "튀김전러버", "뜨끈보양파", "진한메인파",
    "단짠간식파", "해장파",     "슴슴든든파", "따뜻집밥파",
]


def _user_display(uid: int) -> str:
    """user_id → 카드에 보일 이름. 시연 3명은 친근 이름, 나머지는 페르소나#N."""
    if uid in _USER_DISPLAY_NAMES:
        return _USER_DISPLAY_NAMES[uid]
    if 1 <= uid <= 80:
        type_idx = (uid - 1) // 10
        seq = (uid - 1) % 10 + 1
        return f"{_PERSONA_LABELS[type_idx]}#{seq}"
    return f"사용자{uid}"


def _build_supporters_desc(supporter_uids: list[int]) -> str:
    """supporters user_id 리스트 → 'Charlie·매운국물파#5 등 8명이 선택' 문장.

    시연 사용자(Alice·Bob·Charlie)는 *최우선*으로 보여주고, 그 다음은 supporters
    순서대로. 상위 2명까지 이름 + 나머지는 '등 N명'.
    """
    n = len(supporter_uids)
    if n == 0:
        return ""
    # 시연 사용자가 supporters 에 있으면 맨 앞으로 끌어옴
    demo_ids = [uid for uid in supporter_uids if uid in _USER_DISPLAY_NAMES]
    other_ids = [uid for uid in supporter_uids if uid not in _USER_DISPLAY_NAMES]
    ordered = demo_ids + other_ids
    top_named = [_user_display(uid) for uid in ordered[:2]]
    if n <= 2:
        return f"{'·'.join(top_named)}이 선택"
    return f"{'·'.join(top_named)} 등 {n}명이 선택"

app = FastAPI(title="me:nu recommendation API")

# /auth/* 엔드포인트 흡수 (origin/DB 15582c26) — signup·login·me
app.include_router(auth_router)

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
def foods(
    q: str = "",
    tags: str = "",
    food_keywords: str = "",
    top_k: int = 10,
    user_id: int = 1,
):
    """자연어 쿼리 → 기본 추천 (콘텐츠 매칭, match.py).

    두 모드:
      - tags 가 있으면 *extract 건너뛰기* — 사용자가 KeywordScreen 에서 직접
        선택·수정한 시드 태그를 그대로 사용 (사용자 변경이 100% 반영).
        food_keywords 도 같이 받으면 /extract 가 한 번 추출한 카테고리 신호를
        살린다 (Claude 추가 호출 없이 substring 매칭 강화).
      - tags 없으면 q 로 extract 호출 → 시드 추출 → match (자동 모드).

    파라미터는 콤마 구분: `?tags=얼큰한,야식&food_keywords=찌개,국밥`.
    DB 동적 wiring (Session/Tag/Log/Weight) 양쪽 동일 — 검색마다 INSERT.
    """
    if not q.strip() and not tags.strip():
        raise HTTPException(status_code=400, detail="q or tags required")

    if tags.strip():
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        fkw_list = [t.strip() for t in food_keywords.split(",") if t.strip()]
        result = recommend_foods_by_tags(tag_list, top_k=top_k, food_keywords=fkw_list)
    else:
        result = recommend_foods(q, top_k=top_k)

    # 카드 추천 근거 — '검색 키워드 모두 일치·12개 식당이 판매' 형태.
    # 매칭 강도(왜 추천된 신호) + 데이터 신뢰(식당 검증). CF 탭과 톤 매치.
    total_keywords = len(result.get("keywords", []))
    for k in result.get("kinds", []):
        matched = len((k.get("reason", {}) or {}).get("matchedKeywords", []))
        desc = _build_kind_reason_desc(
            k.get("name", ""), k.get("nStores", 0), matched, total_keywords,
        )
        if desc:
            k.setdefault("reason", {})["cfDescription"] = desc

    session_id = _open_session_and_save_tags(user_id, result.get("keywords", []))
    result["sessionId"] = session_id
    result["userId"] = user_id
    return result


@app.get("/foods_cf")
def foods_cf(
    q: str = "",
    tags: str = "",
    food_keywords: str = "",  # 호환만 — cf_module Tab2 점수엔 미사용. 응답에 echo.
    user_id: int = 1,
    top_k: int = 10,
):
    """개인화 추천 (cf_module Tab2 personalized, 사용자 기반 CF).

    "나와 *행동 윤곽이 닮은 사용자들*이 고른 메뉴". user_id 의 final_select 한 kind 는
    재추천에서 제외 (이미 먹어본 거). click 만 한 kind 는 후보로 남김 (관심 단계).

    두 모드 (/foods 와 동일):
      - tags 가 있으면 *extract 건너뛰기* — 사용자 선택 시드 그대로 cf_module 에 전달
      - tags 없으면 q 로 extract 호출 후 cf_module 호출

    응답 모양은 /foods 와 동일 (kinds[]·sessionId·userId).
    """
    if not q.strip() and not tags.strip():
        raise HTTPException(status_code=400, detail="q or tags required")

    if tags.strip():
        input_tags = [t.strip() for t in tags.split(",") if t.strip()]
    else:
        extracted = extract_tags(q)
        input_tags = list(extracted.tags or [])

    cf_response = cf_recommend(input_tags, user_id=user_id, top_k=top_k)

    # 유사 사용자 N명 + 각 kind 별 *그 중 행동한 사용자 수* 계산 — *진짜 데이터*
    # 근거 문장 (cfDescription) 으로 사용. cf_module 의 _score_candidates 가
    # 내부에서 같은 계산을 하지만 결과를 안 노출해서 여기서 한 번 더 한다.
    similar_users = _cf_find_similar_users(user_id)
    n_similar = len(similar_users)
    rep_tags = _get_kind_rep_tags()
    kinds = _cf_results_to_kinds(cf_response.tab2_results, rep_tags)
    # 각 kind 의 supporters 수 + 이름 = 유사 사용자 중 이 kind 에 행동한 사람들
    for kind_dict, r in zip(kinds, cf_response.tab2_results):
        supporter_uids = [
            uid for uid, _sim in similar_users
            if _cf_user_kind_weight(uid, r.kind_id) > 0
        ]
        n_supporters = len(supporter_uids)
        kind_dict["reason"]["cfDescription"] = _build_supporters_desc(supporter_uids)
        kind_dict["reason"]["cfSupporters"] = n_supporters
        kind_dict["reason"]["cfSimilarUsers"] = n_similar
        kind_dict["reason"]["cfSupporterNames"] = [_user_display(uid) for uid in supporter_uids]

    session_id = _open_session_and_save_tags(user_id, input_tags)
    return {
        "query": q,
        "userId": user_id,
        "sessionId": session_id,
        "keywords": input_tags,
        "kinds": kinds,
        "emptyReason": cf_response.tab2_empty_reason,
    }


def _user_final_foods(conn, user_id: int) -> list[str]:
    """그 사용자가 최종선택(final_select)한 음식 종류 목록 (중복 제거, food_id 순)."""
    rows = conn.execute(
        """
        SELECT DISTINCT f.food_name, f.food_id
          FROM UserInteractionLog l
          JOIN RecommendationSession rs ON rs.session_id = l.session_id
          JOIN Food f ON f.food_id = l.food_id
         WHERE rs.user_id = ? AND l.action_type = 'final_select'
         ORDER BY f.food_id
        """,
        (user_id,),
    ).fetchall()
    return [r[0] for r in rows]


def _shared_foods(user_id: int, other_id: int, limit: int = 3) -> list[str]:
    """두 사용자가 *둘 다* 최종선택한 음식 (왜 닮았는지 보여주는 교집합).

    교집합이 비면(예: 본인 이력이 적음) 상대방 음식 일부로 폴백.
    """
    try:
        conn = _connect_recommend_db()
        try:
            mine = _user_final_foods(conn, user_id)
            theirs = _user_final_foods(conn, other_id)
        finally:
            conn.close()
        mine_set = set(mine)
        shared = [f for f in theirs if f in mine_set]
        result = shared if shared else theirs
        return result[:limit]
    except Exception:
        return []


@app.get("/similar_users")
def similar_users(user_id: int = 1, top_k: int = 5):
    """나와 취향이 닮은 사용자 — user-based CF 유사도 상위 K명.

    마이페이지에서 'Charlie와 56% 닮았어요 · 짬뽕·육개장을 골랐어요' 식으로
    노출. CF 가 추상 알고리즘이 아니라 *눈에 보이는 기능*임을 보여주는 자리.
    cold start(행동 이력 0)면 users=[] — 프론트가 '아직 닮은 사용자 없음' 폴백.

    match = jaccard 유사도 × 100 (정직한 raw 값). topFoods = 그 사람이 최종선택한
    음식 종류 상위 3개.
    """
    try:
        sims = _cf_find_similar_users(user_id)  # [(uid, sim), ...] 내림차순
    except Exception:
        sims = []
    users = []
    for uid, sim in sims[:top_k]:
        if sim <= 0:
            continue
        users.append({
            "userId": uid,
            "name": _user_display(uid),
            "match": round(sim * 100),
            "sharedFoods": _shared_foods(user_id, uid, limit=3),
        })
    return {"userId": user_id, "users": users}


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


# 식당 CF 점수 캐시 — store_id 별 메뉴 kind 리스트. load_menu_tags() 결과
# 한 번 빌드해 두면 모든 /restaurants 호출에 재사용.
_STORE_KINDS_CACHE: dict[int, list[str]] | None = None


def _get_store_kinds() -> dict[int, list[str]]:
    """store_id → 그 식당의 모든 메뉴 kind 리스트 (중복 포함)."""
    global _STORE_KINDS_CACHE
    if _STORE_KINDS_CACHE is None:
        bag: dict[int, list[str]] = {}
        for r in load_menu_tags():
            if r.kind and r.store_id:
                bag.setdefault(r.store_id, []).append(r.kind)
        _STORE_KINDS_CACHE = bag
    return _STORE_KINDS_CACHE


def _kind_name_to_food_id() -> dict[str, int]:
    """kind 이름 → recommend.db Food.food_id. cf_module 의 _KINDS 그대로."""
    from cf_module.core.recommend import _KINDS
    return {k.name: k.kind_id for k in _KINDS}


def _compute_store_cf_scores(user_id: int, store_ids: list[int]) -> dict[int, float]:
    """각 식당의 cfScore = Σ(메뉴 distinct kind 별 *유사 사용자 행동 가중치 합*).

    의미: 내 유사 사용자들이 *이 식당이 다루는 음식들*을 얼마나 좋아했나.
    식당마다 메뉴 구성 다르므로 자연스럽게 식당별 점수 차별화.
    """
    similar = _cf_find_similar_users(user_id)
    if not similar:
        return {sid: 0.0 for sid in store_ids}

    store_kinds = _get_store_kinds()
    name_to_kind_id = _kind_name_to_food_id()

    scores: dict[int, float] = {}
    for sid in store_ids:
        score = 0.0
        # distinct kind — 한 식당이 김치찌개 메뉴 3개 있어도 *김치찌개 1번*만 카운트
        for kind_name in set(store_kinds.get(sid, [])):
            kind_id = name_to_kind_id.get(kind_name)
            if kind_id is None:
                continue
            for uid, sim in similar:
                w = _cf_user_kind_weight(uid, kind_id)
                if w > 0:
                    score += sim * w
        scores[sid] = score
    return scores


@app.get("/restaurants")
def restaurants(q: str, kind: str, top_k: int = 10, user_id: int = 1):
    """선택한 음식 종류 → 그 종류의 식당 추천 (2차).

    q는 1차에서 쓴 쿼리 그대로 — 사용자 취향이 식당 점수에 반영되도록.
    user_id 로 *식당별 cfScore* 계산 → 응답에 같이 노출. 프론트가 '취향 맞춤'
    탭에서 cfScore 정렬 + cfMatch 시각화에 사용.
    응답 stores[] 각 item에 baeminUrl 주입 (시연용 매핑에 있는 식당만).
    """
    if not q.strip() or not kind.strip():
        raise HTTPException(status_code=400, detail="q and kind required")
    result = recommend_stores_for_kind(q, kind, top_k=top_k)

    # CF 점수 — 모든 식당 일괄 계산 후 최댓값으로 정규화 (cfMatch 0~1)
    stores = result.get("stores", [])
    store_ids = [int(s["storeId"]) for s in stores if s.get("storeId")]
    cf_scores = _compute_store_cf_scores(user_id, store_ids)
    max_cf = max(cf_scores.values(), default=0.0) or 1.0

    baemin_urls = _load_baemin_urls()
    for store in stores:
        sid = int(store.get("storeId") or 0)
        raw = cf_scores.get(sid, 0.0)
        store["cfScore"] = round(raw, 3)
        store["cfMatch"] = round(raw / max_cf, 3) if max_cf > 0 else 0.0
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
