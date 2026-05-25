"""쿼리 태그 ↔ 메뉴 태그 매칭 — 후보 메뉴 K개 추출.

파이프라인 매칭 단계. LLM 호출 없음(순수 계산)이라 API 키와 무관하게 동작한다.
입력 태그의 출처(mock/휴리스틱 vs Claude)가 좋아지면 결과도 그대로 좋아진다.

    extract.py  → 쿼리 태그 ┐
                            ├→ match.py(점수) → 후보 K개 → (이후 CF 재랭킹)
    enrich.py   → 메뉴 태그 ┘

점수(v1): query 커버리지(교집합/쿼리태그수) 우선, 동점 시 food_kw 메뉴명 매칭 수,
다시 동점 시 Jaccard.
  - 커버리지: 사용자가 원한 것 중 이 메뉴가 몇 개를 충족하나
  - food_kw 매칭: 카테고리·식재료 단어(고기/면/회/치킨…)가 메뉴명에 들어있는지.
    시드는 '속성'만 다루므로 카테고리축은 메뉴명 substring으로 보완 (§8.11 카테고리축
    부재 문제 해법). 시드 외 단어를 별도 채널로 받아 시드 의미론을 오염시키지 않는다.
  - Jaccard 동점 처리: 군더더기 태그가 적어 더 '집중된' 매칭을 선호

태그가 비어 있어도(쿼리에 '회/면' 단독처럼 시드 매핑 불가) food_keywords만으로
매칭이 가능하다 — cat-* 케이스가 빈 결과 안 나오게.
튜닝 여지(§6): 희소 태그 IDF 가중(해장·쫄깃한이 든든한·국물있는보다 변별력↑) 등.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .tags import normalize

_HERE = Path(__file__).resolve().parent
DEFAULT_MENU_TAGS = _HERE / "data" / "menu_tags.jsonl"


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


@dataclass
class MatchResult:
    store_id: int
    menu_name: str
    category: str | None
    tags: list[str]
    matched: list[str]  # 쿼리와 겹친 태그
    overlap: int
    jaccard: float
    coverage: float  # 쿼리 태그 중 충족 비율 (0~1)
    score: float
    matched_food_keywords: list[str] = None  # type: ignore[assignment]
    food_kw_hits: int = 0  # 메뉴명에 들어간 food_keyword 개수(중복 제거)

    def __post_init__(self) -> None:
        if self.matched_food_keywords is None:
            self.matched_food_keywords = []


def load_menu_tags(path: Path = DEFAULT_MENU_TAGS) -> list[MenuRow]:
    """enrich.py가 만든 menu_tags.jsonl 로드. 태그 없는 메뉴는 매칭 불가라 제외."""
    rows: list[MenuRow] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if not d.get("tags"):
                continue
            rows.append(
                MenuRow(
                    store_id=int(d["store_id"]),
                    menu_name=d["menu_name"],
                    category=d.get("category"),
                    tags=list(d["tags"]),
                )
            )
    return rows


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

    results: list[MatchResult] = []
    for row in menu_rows:
        m = {normalize(t) for t in row.tags}
        if excl & m:
            continue  # 시드 부정: 거부된 시드가 메뉴에 있으면 제외
        name_lower = row.menu_name.lower()
        if any(k in name_lower for k in excl_fkw):
            continue  # 카테고리 부정: 거부된 음식 종류가 메뉴명에 있으면 제외

        inter = q & m
        overlap = len(inter)
        # 메뉴명에 들어간 food_kw 수집 (중복 제거)
        matched_fkw = [k for k in fkw if k in name_lower]
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
        # food_kw 보너스: 매칭당 +0.25, 상한 +0.5. 커버리지 1칸(0.25)보다 작아서 태그
        # 우위는 보존되되, 동률 후보 사이에서는 food_kw 매칭이 결정적 신호가 된다.
        food_bonus = min(fkw_hits, 2) * 0.25
        score = coverage + food_bonus + jaccard * 1e-3
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
                score=round(score, 4),
                matched_food_keywords=matched_fkw,
                food_kw_hits=fkw_hits,
            )
        )

    # 정렬: 태그가 있으면 (overlap → food_kw → jaccard), 없으면 (food_kw → jaccard).
    # 태그 매칭이 의도의 1차 신호라 우선, food_kw는 동률 깨기와 카테고리 보강용.
    if q:
        results.sort(
            key=lambda r: (r.overlap, r.food_kw_hits, r.jaccard), reverse=True
        )
    else:
        results.sort(key=lambda r: (r.food_kw_hits, r.jaccard), reverse=True)
    return results[:top_k]


def to_food(r: MatchResult) -> dict:
    """MatchResult → 프론트 food 객체 계약 (foods.mock.js 형태).

    reason의 cfScore/cfDescription/contextNote는 이후 단계(CF 등)가 채울 빈 칸.
    여기선 matchedKeywords와 매칭 기반 score만 채운다.
      - storeId: 프론트 mock엔 없지만 식당 집계·연결에 필수라 확장 필드로 포함
      - score: 0~100. CF 합류 전 임시값. match()의 정렬 키 (overlap, jaccard)를
        그대로 반영하도록 커버리지(0.85)+Jaccard(0.15) 가중 합으로 산출한다.
        커버리지만 쓰면 태그를 다 충족한 후보가 전부 100점으로 몰려 순위 정보가
        사라지므로, Jaccard를 섞어 프론트가 score로 재정렬해도 같은 순서가 나오게 한다.
        (extract가 쿼리 태그를 최대 4개로 캡 → 커버리지 한 칸 차이 ≥ 21점 > Jaccard
        기여 최대 15점이라 '커버리지 우선, Jaccard 동점처리' 순서가 보존됨.)
    """
    return {
        "id": stable_food_id(r.store_id, r.menu_name),
        "storeId": r.store_id,
        "name": r.menu_name,
        "tags": r.tags,
        "score": round((min(r.coverage, 1.0) * 0.85 + r.jaccard * 0.15) * 100),
        "reason": {
            "matchedKeywords": r.matched,
            "matchedFoodKeywords": r.matched_food_keywords,  # 메뉴명에 잡힌 음식 종류
            "cfScore": None,        # CF가 채움 (CF_hw)
            "cfDescription": None,  # CF가 채움
            "contextNote": None,    # 이후 단계가 채울 빈 칸
        },
    }


def recommend_foods(query_text: str, top_k: int = 10) -> dict:
    """자연어 → 프론트 계약 그대로의 추천 응답. extract→match→food 객체.

    반환: {"query", "keywords", "excludeKeywords", "foodKeywords",
           "excludeFoodKeywords", "foods": [food 객체...]}
    cfScore/contextNote는 빈 칸 — 이후 CF 단계가 같은 객체를 채운다.
    excludeKeywords/excludeFoodKeywords가 비어있지 않으면 프론트가
    "X 빼고 추천" 표기를 할 수 있다.
    """
    extracted, results = _recommend_extracted(query_text, top_k=top_k)
    return {
        "query": query_text,
        "keywords": extracted.tags,
        "excludeKeywords": extracted.exclude_tags,
        "foodKeywords": extracted.food_keywords,
        "excludeFoodKeywords": extracted.exclude_food_keywords,
        "foods": [to_food(r) for r in results],
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
    print(f"(매칭 대상 메뉴: {len(rows)}개)\n")
    for qtext in queries:
        extracted, results = _recommend_extracted(qtext, top_k=8)
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
        for r in results:
            fkw_label = f" food✓{r.matched_food_keywords}" if r.matched_food_keywords else ""
            print(
                f"    [{r.score:.3f}] store{r.store_id:<4d} {r.menu_name[:24]:24s}"
                f" 매칭{r.matched} 메뉴태그{r.tags}{fkw_label}"
            )
        print()

    # 프론트 계약(food 객체) 출력 샘플 — 첫 쿼리
    print("=" * 60)
    print(f"프론트 계약 형태 (recommend_foods) — {queries[0]!r}")
    sample = recommend_foods(queries[0], top_k=2)
    print(json.dumps(sample, ensure_ascii=False, indent=2))
