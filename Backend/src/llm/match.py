"""쿼리 태그 ↔ 메뉴 태그 매칭 — 후보 메뉴 K개 추출.

파이프라인 매칭 단계. LLM 호출 없음(순수 계산)이라 API 키와 무관하게 동작한다.
입력 태그의 출처(mock/휴리스틱 vs Claude)가 좋아지면 결과도 그대로 좋아진다.

    extract.py  → 쿼리 태그 ┐
                            ├→ match.py(점수) → 후보 K개 → (이후 CF 재랭킹)
    enrich.py   → 메뉴 태그 ┘

점수(v2): IDF 가중 커버리지 + food_kw 매칭 비율 + Jaccard + 사이드 디부스트.
  - weighted_coverage: 쿼리 태그를 idf 가중치로 평균 — 흔한 시드(든든한 2236건,
    고소한 2244건)는 변별력 약, 희소 시드(해장 261건, 쫄깃한 461건)는 강. 단일 시드
    쿼리("든든한 한 끼")에서 모든 메뉴가 cov=1.0으로 동률나던 문제를 완화.
  - food_ratio: hits / len(fkw) — 비율이라 자연 상한 1. score·정렬·to_food 모두 동일
    공식 사용 (§5.10 (1) 단일화).
  - jaccard: 동률 깨기. 군더더기 태그가 적어 더 '집중된' 매칭을 선호.
  - side 디부스트: 메뉴명에 '추가/사리/즉석/공기/리필'이 들어가면 score × 0.5.
    사이드/추가 메뉴가 단태그로 jaccard=1.0이 되어 1위 도배하던 자리(§5.10 별개 사항).

부정 채널은 기존과 동일 — exclude_tags는 시드 교집합 hard filter, exclude_food_keywords는
메뉴명+카테고리 substring hard filter.

태그가 비어 있어도(쿼리에 '회/면' 단독처럼 시드 매핑 불가) food_keywords만으로
매칭이 가능하다 — cat-* 케이스가 빈 결과 안 나오게.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .kinds import KIND_OTHER, KIND_OTHER_ALCOHOL, KIND_OTHER_BEVERAGE, KIND_OTHER_SIDE
from .tags import normalize

_HERE = Path(__file__).resolve().parent
DEFAULT_MENU_TAGS = _HERE / "data" / "menu_tags.jsonl"
DEFAULT_MENU_KINDS = _HERE / "data" / "menu_kinds.jsonl"

# 추천 메인에서 빠지는 종류 — 사이드/음료/주류/분류불가. 사용자가 '추천해줘' 했을 때
# 식사 의도가 분명하니 음료·주류는 메인 후보 풀에서 제외. '기타'(분류 불가)도 의미가
# 약해 함께 제외 — 진짜 추천할 가치 있는 종류만 추천 단위로 노출.
_HIDDEN_KINDS = {KIND_OTHER, KIND_OTHER_BEVERAGE, KIND_OTHER_ALCOHOL, KIND_OTHER_SIDE}
# store_id → 식당 이름 조회용. menu_tags.jsonl은 enrich 결과만 보관하고, 식당명은
# details.db에서 join해 가져온다 (responsibility 분리). 사용자가 식별 가능한 메뉴명이
# 식당에 따라 모호한 경우("잘빠진세트", "패밀리세트 3인")가 있어 응답에 식당명 동봉.
DEFAULT_DETAILS_DB = _HERE / ".." / ".." / "db" / "details.db"

# 사이드/추가 메뉴 패턴 — 메뉴명에 들어가면 score × 0.5 (단태그 도배 방지).
# 단어 단위로 잡되 한국어는 형태소 경계가 약해서 단순 substring으로 충분히 정확.
# 후보 검증: '공기밥/공깃밥/즉석밥/사리추가/공기밥 추가/햄추가/리필'.
# '세트/셋트'는 정찬 메뉴 표지도 되어 제외 (디부스트 시 false-positive 큼).
_SIDE_PATTERN = re.compile(r"(추가|사리|즉석|공기|공깃|리필)")
_SIDE_PENALTY = 0.5

# 점수 공식의 가중치 — score·정렬·to_food 모두 같은 식으로 일관 적용 (§5.10 (1)).
# weighted_coverage가 1차 신호(태그 의도), food_ratio는 2차(카테고리 보강),
# jaccard는 동률 깨기. food 비중을 0.3으로 두면 fkw 2개+coverage 1 = 1.6 정도가
# coverage 1만 있는 후보(1.0)보다 크게 위로 나와 카테고리 신호가 살아난다.
_W_TAG = 1.0
_W_FOOD = 0.5
_W_JAC = 0.1


def stable_food_id(store_id: int, menu_name: str) -> str:
    """(store_id, menu_name) → 결정적 메뉴 id. 프론트 'food-xxx' 식별자 계약과 호환.

    크롤링 메뉴엔 frontend foods.mock.js 같은 id가 없다. (store_id, menu_name)으로부터
    해시를 만들어 재실행/누가 계산하든 같은 id가 나오게 한다 (카운터 불필요).
    """
    h = hashlib.sha1(f"{store_id}|{menu_name}".encode("utf-8")).hexdigest()[:10]
    return f"food-{h}"


@dataclass
class MenuRow:
    store_id: int
    menu_name: str
    category: str | None
    tags: list[str]
    store_name: str | None = None
    kind: str | None = None  # menu_kinds.jsonl에서 join (§5.12 추천 단위)


@dataclass
class MatchResult:
    store_id: int
    menu_name: str
    category: str | None
    tags: list[str]
    matched: list[str]  # 쿼리와 겹친 태그
    overlap: int
    jaccard: float
    coverage: float  # 쿼리 태그 중 충족 비율 (0~1) — 디버그용 raw 값
    weighted_coverage: float  # idf 가중 커버리지 (0~1) — 정렬/점수의 1차 키
    score: float
    is_side: bool = False  # 사이드/추가 메뉴 여부 — 디부스트 적용됨
    matched_food_keywords: list[str] = None  # type: ignore[assignment]
    food_kw_hits: int = 0  # 메뉴명에 들어간 food_keyword 개수(중복 제거)
    store_name: str | None = None  # details.db에서 join. 모호한 메뉴명 식별용
    kind: str | None = None  # 음식 종류 (§5.12). 집계 시 그룹 키

    def __post_init__(self) -> None:
        if self.matched_food_keywords is None:
            self.matched_food_keywords = []


@dataclass
class KindGroup:
    """음식 종류 단위 집계 결과 — 추천 1차 단위 (§5.12).

    같은 종류의 메뉴들을 묶고, 그 종류의 대표 점수(=가장 높은 메뉴 점수)와
    어떤 식당에서 어떤 메뉴로 잡혔는지 리스트를 담는다.
    """
    kind: str
    score: float            # max(메뉴 score) — 종류의 대표 점수
    weighted_coverage: float
    food_kw_hits: int
    jaccard: float
    matched: list[str]              # union of menu matched tags
    matched_food_keywords: list[str]
    menus: list[MatchResult]        # score 내림차순. 모든 매칭 메뉴
    n_stores: int                   # distinct store_id 수


def compute_idf(rows: list[MenuRow]) -> dict[str, float]:
    """메뉴 분포 기반 시드 태그 IDF.

    df(t) = 태그 t를 가진 메뉴 수, N = 전체 매칭 가능 메뉴 수.
    idf(t) = log((N+1)/(df+1)) — 흔한 태그는 작고, 희소 태그는 크다.

    현재 데이터(N=4774): 든든한 2236 → 0.76, 해장 261 → 2.90.
    단일 시드 쿼리에서 흔한 태그(든든한) 매칭으로는 weighted_coverage가 잘 안 오르고,
    희소 태그(해장) 매칭은 강하게 인정되어 진짜 변별력 있는 신호로 작동.
    """
    df: Counter[str] = Counter()
    n = len(rows)
    for r in rows:
        for t in {normalize(x) for x in r.tags}:
            df[t] += 1
    return {t: math.log((n + 1) / (c + 1)) for t, c in df.items()}


_IDF_CACHE: dict[str, float] | None = None


def _get_idf(rows: list[MenuRow]) -> dict[str, float]:
    global _IDF_CACHE
    if _IDF_CACHE is None:
        _IDF_CACHE = compute_idf(rows)
    return _IDF_CACHE


_STORE_NAME_CACHE: dict[int, str] | None = None


def _load_store_names(db_path: Path = DEFAULT_DETAILS_DB) -> dict[int, str]:
    """details.db에서 store_id → name 매핑. 한 번 읽고 모듈 캐싱.

    enrich 결과(menu_tags.jsonl)는 LLM 태깅 산출물만 들고, 식당명은 source-of-truth인
    details.db에서 join한다. 식당명 바뀌면 캐시 reset 후 재실행.
    """
    global _STORE_NAME_CACHE
    if _STORE_NAME_CACHE is not None:
        return _STORE_NAME_CACHE
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT store_id, name FROM stores")
        _STORE_NAME_CACHE = {int(sid): name for sid, name in cur.fetchall()}
    finally:
        conn.close()
    return _STORE_NAME_CACHE


def _load_menu_kinds(path: Path = DEFAULT_MENU_KINDS) -> dict[tuple[int, str], str]:
    """menu_kinds.jsonl → (store_id, menu_name) → kind 매핑.

    enrich_kinds.py 산출물. menu_tags.jsonl과 같은 키 구조라 (store_id, menu_name)으로 join.
    """
    if not path.exists():
        return {}
    out: dict[tuple[int, str], str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out[(int(d["store_id"]), d["menu_name"])] = d["kind"]
    return out


def load_menu_tags(path: Path = DEFAULT_MENU_TAGS) -> list[MenuRow]:
    """enrich.py가 만든 menu_tags.jsonl 로드. 태그 없는 메뉴는 매칭 불가라 제외.

    details.db에서 store_name도 함께 join. menu_kinds.jsonl이 있으면 kind 필드도 채움.
    """
    store_names = _load_store_names()
    kinds = _load_menu_kinds()
    rows: list[MenuRow] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if not d.get("tags"):
                continue
            sid = int(d["store_id"])
            mname = d["menu_name"]
            rows.append(
                MenuRow(
                    store_id=sid,
                    menu_name=mname,
                    category=d.get("category"),
                    tags=list(d["tags"]),
                    store_name=store_names.get(sid),
                    kind=kinds.get((sid, mname)),
                )
            )
    return rows


def aggregate_kinds(
    results: list[MatchResult],
    top_k: int = 10,
    hidden_kinds: set[str] | None = None,
) -> list[KindGroup]:
    """메뉴 단위 매칭 결과 → 음식 종류 단위 집계 (§5.12).

    같은 kind의 메뉴들을 묶어 그룹을 만든다. 종류의 대표 점수는 *그 종류 안의 가장 높은
    메뉴 점수*. 평균이나 합계가 아니라 max인 이유: 한 종류에서 한 메뉴만 강하게 매칭돼도
    그 종류가 추천에 떠야 함 (희소·신선한 매칭의 가치). 평균은 흔한 종류에 불리.

    제외 종류 (KIND_OTHER_*): 사이드·음료·주류·분류불가. 식사 추천에서 의미 약함.
    kind가 None(menu_kinds.jsonl join 실패)인 메뉴도 제외 — 분류 안 된 건 추천 단위 미정.
    """
    if hidden_kinds is None:
        hidden_kinds = _HIDDEN_KINDS

    grouped: dict[str, list[MatchResult]] = {}
    for r in results:
        if not r.kind or r.kind in hidden_kinds:
            continue
        grouped.setdefault(r.kind, []).append(r)

    groups: list[KindGroup] = []
    for kind, menus in grouped.items():
        menus.sort(key=lambda m: m.score, reverse=True)
        top = menus[0]
        # union: 그 종류 안에서 잡힌 모든 매칭 태그/food_kw 합집합
        all_matched = sorted({t for m in menus for t in m.matched})
        all_fkw = sorted({k for m in menus for k in m.matched_food_keywords})
        n_stores = len({m.store_id for m in menus})
        groups.append(
            KindGroup(
                kind=kind,
                score=top.score,
                weighted_coverage=top.weighted_coverage,
                food_kw_hits=top.food_kw_hits,
                jaccard=top.jaccard,
                matched=all_matched,
                matched_food_keywords=all_fkw,
                menus=menus,
                n_stores=n_stores,
            )
        )

    # 종류별 정렬 — 메뉴와 같은 키 다음에 *대표성*으로 동률 깨기.
    # 같은 점수면 메뉴 수가 많은 종류, 그 다음 식당 수 많은 종류를 위로. 단태그 단일
    # 메뉴(잘빠진세트 한정식 1점)가 다태그 다수(육개장 7점)와 동점인 자리에서 후자가
    # 위로 오게 — '같은 점수면 더 흔하게 잘 잡히는 종류가 신뢰 가능'이라는 직관.
    groups.sort(
        key=lambda g: (
            g.score,
            g.weighted_coverage,
            g.food_kw_hits,
            g.jaccard,
            len(g.menus),
            g.n_stores,
        ),
        reverse=True,
    )
    return groups[:top_k]


def match(
    query_tags: list[str],
    menu_rows: list[MenuRow],
    top_k: int = 20,
    min_overlap: int = 1,
    exclude_tags: list[str] | None = None,
    food_keywords: list[str] | None = None,
    exclude_food_keywords: list[str] | None = None,
) -> list[MatchResult]:
    """쿼리 태그로 메뉴 후보를 점수화해 상위 top_k 반환.

    - 양쪽 태그를 normalize로 정규형 통일 후 집합 비교 (방어적).
    - exclude_tags ∩ 메뉴태그 → hard filter (시드 차원 부정).
    - exclude_food_keywords ∩ 메뉴명 substring → hard filter (카테고리 차원 부정).
    - food_keywords substring 매칭은 score 보너스 + 정렬 2차 키.
      쿼리 태그가 비어 있으면(시드 매핑 불가 쿼리) food_kw만으로 후보를 만들 수 있다.
    """
    q = {normalize(t) for t in query_tags if t and t.strip()}
    excl = {normalize(t) for t in (exclude_tags or []) if t and t.strip()}
    # food_kw는 메뉴명 substring 매칭이라 lowercase로만 비교.
    # 한국어 1글자 음식어("회/면/밥")가 핵심 신호라 길이 필터 없이 빈 문자열만 거른다.
    fkw = [k.strip().lower() for k in (food_keywords or []) if k and k.strip()]
    excl_fkw = [
        k.strip().lower()
        for k in (exclude_food_keywords or [])
        if k and k.strip()
    ]
    if not q and not fkw:
        return []

    idf = _get_idf(menu_rows)
    # idf 모르는 토큰(쿼리에만 등장하는 정규화 외 어휘)은 평균 idf로 — 무리한 가중 회피.
    default_idf = sum(idf.values()) / len(idf) if idf else 1.0
    q_idf_sum = sum(idf.get(t, default_idf) for t in q) if q else 0.0
    n_fkw = len(fkw)

    results: list[MatchResult] = []
    for row in menu_rows:
        m = {normalize(t) for t in row.tags}
        if excl & m:
            continue  # 시드 부정: 거부된 시드가 메뉴에 있으면 제외
        # substring 매칭 대상은 메뉴명 + 식당 카테고리(네이버 플레이스 업종).
        # 메뉴 이름은 식재료축('갈비탕·라면·참치회덮밥')을, category는 장르축
        # ('한식·중식·일식·분식')을 담는 별개 신호. 두 축 모두 무료로 잡힌다.
        haystack = (row.menu_name + " " + (row.category or "")).lower()
        if any(k in haystack for k in excl_fkw):
            continue  # 카테고리 부정: 거부된 음식 종류가 어느 한 곳에 있으면 제외

        inter = q & m
        overlap = len(inter)
        # haystack에 들어간 food_kw 수집 (중복 제거)
        matched_fkw = [k for k in fkw if k in haystack]
        fkw_hits = len(matched_fkw)

        # 후보 조건: tag overlap이 임계 이상이거나, 태그가 비어있을 땐 food_kw 매칭 있으면 OK.
        if q:
            if overlap < min_overlap:
                continue
        else:
            if fkw_hits == 0:
                continue

        union = len(q | m)
        jaccard = overlap / union if union else 0.0
        coverage = (overlap / len(q)) if q else 0.0
        # idf 가중 커버리지 — 흔한 태그 매칭은 점수 약, 희소 태그 매칭은 강.
        if q_idf_sum > 0:
            inter_idf = sum(idf.get(t, default_idf) for t in inter)
            weighted_cov = inter_idf / q_idf_sum
        else:
            weighted_cov = 0.0
        # food_kw 매칭 비율 — 자연 상한 1. 사용자가 요청한 카테고리 단어를 메뉴가 몇 % 충족.
        food_ratio = (fkw_hits / n_fkw) if n_fkw else 0.0
        # 사이드 디부스트 — 메뉴명에 '추가/사리/공기' 등 들어가면 점수 절반.
        is_side = bool(_SIDE_PATTERN.search(row.menu_name))
        base = _W_TAG * weighted_cov + _W_FOOD * food_ratio + _W_JAC * jaccard
        score = base * (_SIDE_PENALTY if is_side else 1.0)

        results.append(
            MatchResult(
                store_id=row.store_id,
                menu_name=row.menu_name,
                category=row.category,
                tags=row.tags,
                matched=sorted(inter),
                overlap=overlap,
                jaccard=round(jaccard, 3),
                coverage=round(coverage, 3),
                weighted_coverage=round(weighted_cov, 3),
                score=round(score, 4),
                is_side=is_side,
                matched_food_keywords=matched_fkw,
                food_kw_hits=fkw_hits,
                store_name=row.store_name,
                kind=row.kind,
            )
        )

    # 정렬: score 단일 키. 사이드 디부스트는 이미 score에 반영됨.
    # score 동률이면 weighted_coverage·food_kw_hits·jaccard 순으로 결정.
    results.sort(
        key=lambda r: (r.score, r.weighted_coverage, r.food_kw_hits, r.jaccard),
        reverse=True,
    )
    return results[:top_k]


def _to_score100(score: float) -> int:
    """score(0~1.6) → 0~100 정규화. _W_TAG+_W_FOOD+_W_JAC를 분모로 (§5.10 단일화)."""
    denom = _W_TAG + _W_FOOD + _W_JAC
    return round(min(score / denom, 1.0) * 100)


def to_food(r: MatchResult) -> dict:
    """MatchResult → 프론트 food 객체 계약 (foods.mock.js 형태).

    reason의 cfScore/cfDescription/contextNote는 이후 단계(CF 등)가 채울 빈 칸.
    여기선 matchedKeywords와 매칭 기반 score만 채운다.
      - storeId: 프론트 mock엔 없지만 식당 집계·연결에 필수라 확장 필드로 포함
      - score: 0~100. match()의 score와 같은 식으로 0~100 정규화 (§5.10 단일화).
        분모 = _W_TAG + _W_FOOD + _W_JAC. 사이드 디부스트도 동일 적용되어
        프론트가 score로 재정렬해도 match()의 순서가 그대로 보존된다.
      - kind: 음식 종류 (§5.12). 같은 종류 메뉴를 프론트가 묶을 수 있게 노출.
    """
    return {
        "id": stable_food_id(r.store_id, r.menu_name),
        "storeId": r.store_id,
        "storeName": r.store_name,
        "name": r.menu_name,
        "kind": r.kind,
        "tags": r.tags,
        "score": _to_score100(r.score),
        "reason": {
            "matchedKeywords": r.matched,
            "matchedFoodKeywords": r.matched_food_keywords,
            "cfScore": None,        # CF가 채움 (CF_hw)
            "cfDescription": None,  # CF가 채움
            "contextNote": None,    # 이후 단계가 채울 빈 칸
        },
    }


def to_kind_group(g: KindGroup) -> dict:
    """KindGroup → 프론트 노출 객체. 추천 1차 단위 (§5.12).

    프론트에서 "[김치찌개] 8개 식당" 같은 카드로 노출, 클릭하면 안쪽 stores 열어서
    실제 메뉴·식당 목록 보여준다. score는 to_food와 같은 0~100 정규화.
    """
    return {
        "kind": g.kind,
        "score": _to_score100(g.score),
        "nStores": g.n_stores,
        "nMenus": len(g.menus),
        "reason": {
            "matchedKeywords": g.matched,
            "matchedFoodKeywords": g.matched_food_keywords,
        },
        # 안쪽 메뉴 리스트 — 같은 종류 안의 식당/메뉴 펼침. score 내림차순.
        "menus": [
            {
                "storeId": m.store_id,
                "storeName": m.store_name,
                "menuName": m.menu_name,
                "score": _to_score100(m.score),
                "tags": m.tags,
                "foodId": stable_food_id(m.store_id, m.menu_name),
            }
            for m in g.menus
        ],
    }


def recommend_foods(
    query_text: str, top_k: int = 10, top_k_kinds: int = 10
) -> dict:
    """자연어 → 프론트 계약 그대로의 추천 응답. extract→match→food 객체.

    반환: {"query", "keywords", "excludeKeywords", "foodKeywords",
           "excludeFoodKeywords", "kinds": [...], "foods": [food 객체...]}

    kinds (§5.12): 추천 1차 단위. 음식 종류로 집계된 결과. 사이드/음료/주류 제외.
    foods: 기존 메뉴 단위 결과. 프론트 호환·CF 재랭킹 입력으로 그대로 유지.
    cfScore/contextNote는 빈 칸 — 이후 CF 단계가 채운다.
    """
    # 종류 집계용으로 메뉴를 넓게 가져오고(top_k_kinds * 8), 별도로 foods 리스트도 만든다.
    # 종류 집계 시 사이드/음료가 제외되니 후보를 충분히 잡아야 좋은 종류가 묻히지 않음.
    extracted, wide_results = _recommend_extracted(query_text, top_k=top_k_kinds * 8)
    kinds = aggregate_kinds(wide_results, top_k=top_k_kinds)
    foods_subset = wide_results[:top_k]
    return {
        "query": query_text,
        "keywords": extracted.tags,
        "excludeKeywords": extracted.exclude_tags,
        "foodKeywords": extracted.food_keywords,
        "excludeFoodKeywords": extracted.exclude_food_keywords,
        "kinds": [to_kind_group(g) for g in kinds],
        "foods": [to_food(r) for r in foods_subset],
    }


def recommend(query_text: str, top_k: int = 10) -> tuple[list[str], list[MatchResult]]:
    """자연어 한 줄 → (추출된 태그, 매칭된 메뉴 후보). 파이프라인 end-to-end.

    extract → match를 묶는다. 쿼리·메뉴 둘 다 시드 14개 어휘라 교집합 매칭이 잘 정의된다.
    extract가 API 키 유무로 mock/Claude 분기되는 것 외엔 이 함수도 키와 무관.
    부정 시드와 부정 food_keywords는 내부적으로 match에 전달돼 후보에서 제외된다.
    """
    extracted, results = _recommend_extracted(query_text, top_k=top_k)
    return extracted.tags, results


def _recommend_extracted(query_text: str, top_k: int = 10):
    """recommend()와 recommend_foods()의 공통 엔진. ExtractResult를 그대로 노출.

    food_keywords/exclude_food_keywords까지 같이 흘려보내야 match가 카테고리축까지
    고려한다. tags 4채널 + match 결과를 묶어 반환.
    """
    from .extract import extract_tags

    extracted = extract_tags(query_text)
    rows = load_menu_tags()
    results = match(
        extracted.tags,
        rows,
        top_k=top_k,
        exclude_tags=extracted.exclude_tags,
        food_keywords=extracted.food_keywords,
        exclude_food_keywords=extracted.exclude_food_keywords,
    )
    return extracted, results


if __name__ == "__main__":
    import sys

    queries = sys.argv[1:] or [
        "얼큰한 국물",
        "고소한 거",
        "해장되는 거",
        "바삭한 야식",
        "고기 든든하게",  # cat-01: 카테고리축 부재 회귀
        "회 먹고 싶다",   # cat-03: 시드 0매칭 + food_kw 단독
    ]
    rows = load_menu_tags()
    n_kinded = sum(1 for r in rows if r.kind)
    print(f"(매칭 대상 메뉴: {len(rows)}개, 음식 종류 join: {n_kinded}개)\n")
    for qtext in queries:
        extracted, results = _recommend_extracted(qtext, top_k=80)
        excl_part = f"  (제외 {extracted.exclude_tags})" if extracted.exclude_tags else ""
        fkw_part = f"  food={extracted.food_keywords}" if extracted.food_keywords else ""
        excl_fkw_part = (
            f"  exclude_food={extracted.exclude_food_keywords}"
            if extracted.exclude_food_keywords
            else ""
        )
        print(
            f"■ {qtext!r}  →  추출 태그 {extracted.tags}{excl_part}{fkw_part}{excl_fkw_part}"
        )
        if not results:
            print("    (매칭 없음)\n")
            continue
        # 추천 1차 단위 — 음식 종류
        kinds = aggregate_kinds(results, top_k=6)
        print(f"    ── 음식 종류 (추천 단위) ──")
        for g in kinds:
            top = g.menus[0]
            store_label = f"@{top.store_name}" if top.store_name else f"store{top.store_id}"
            fkw_label = f" food✓{g.matched_food_keywords}" if g.matched_food_keywords else ""
            print(
                f"    [{g.score:.3f}] {g.kind:12s} ({g.n_stores}개 식당, {len(g.menus)}개 메뉴)"
                f"  대표: {top.menu_name[:20]:20s} {store_label[:16]:16s}"
                f"  매칭{g.matched}{fkw_label}"
            )
        # 디버그: 메뉴 단위 상위 5
        print(f"    ── 메뉴 단위 (참고) ──")
        for r in results[:5]:
            store_label = f"@{r.store_name}" if r.store_name else f"store{r.store_id}"
            kind_label = f"[{r.kind}]" if r.kind else "[?]"
            fkw_label = f" food✓{r.matched_food_keywords}" if r.matched_food_keywords else ""
            print(
                f"    [{r.score:.3f}] {kind_label:10s} {store_label[:16]:16s} {r.menu_name[:24]:24s}"
                f" 매칭{r.matched}{fkw_label}"
            )
        print()

    # 프론트 계약(food 객체) 출력 샘플 — 첫 쿼리
    print("=" * 60)
    print(f"프론트 계약 형태 (recommend_foods) — {queries[0]!r}")
    sample = recommend_foods(queries[0], top_k=2)
    print(json.dumps(sample, ensure_ascii=False, indent=2))
