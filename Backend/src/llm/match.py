"""쿼리 태그 ↔ 메뉴 태그 매칭 — 후보 메뉴 K개 추출.

파이프라인 매칭 단계. LLM 호출 없음(순수 계산)이라 API 키와 무관하게 동작한다.
입력 태그의 출처(mock/휴리스틱 vs Claude)가 좋아지면 결과도 그대로 좋아진다.

    extract.py  → 쿼리 태그 ┐
                            ├→ match.py(점수) → 후보 K개 → (이후 CF 재랭킹)
    enrich.py   → 메뉴 태그 ┘

점수(v1): query 커버리지(교집합/쿼리태그수) 우선, 동점 시 Jaccard.
  - 커버리지: 사용자가 원한 것 중 이 메뉴가 몇 개를 충족하나
  - Jaccard 동점 처리: 군더더기 태그가 적어 더 '집중된' 매칭을 선호
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
) -> list[MatchResult]:
    """쿼리 태그로 메뉴 후보를 점수화해 상위 top_k 반환.

    양쪽 태그를 normalize로 정규형 통일 후 집합 비교 (방어적).
    """
    q = {normalize(t) for t in query_tags if t and t.strip()}
    if not q:
        return []

    results: list[MatchResult] = []
    for row in menu_rows:
        m = {normalize(t) for t in row.tags}
        inter = q & m
        overlap = len(inter)
        if overlap < min_overlap:
            continue
        union = len(q | m)
        jaccard = overlap / union if union else 0.0
        coverage = overlap / len(q)
        # 커버리지를 주점수로, Jaccard를 소수점 동점처리로 합성
        score = coverage + jaccard * 1e-3
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
            )
        )

    results.sort(key=lambda r: (r.overlap, r.jaccard), reverse=True)
    return results[:top_k]


def to_food(r: MatchResult) -> dict:
    """MatchResult → 프론트 food 객체 계약 (foods.mock.js 형태).

    reason의 cfScore/cfDescription은 CF가, contextNote는 컨텍스트 트랙이 채울 빈 칸.
    여기선 matchedKeywords와 매칭 기반 score만 채운다.
      - storeId: 프론트 mock엔 없지만 식당 집계·연결에 필수라 확장 필드로 포함
      - score: 0~100. CF 합류 전이라 현재는 매칭 커버리지 기반
    """
    return {
        "id": stable_food_id(r.store_id, r.menu_name),
        "storeId": r.store_id,
        "name": r.menu_name,
        "tags": r.tags,
        "score": round(min(r.coverage, 1.0) * 100),
        "reason": {
            "matchedKeywords": r.matched,
            "cfScore": None,        # CF가 채움 (CF_hw)
            "cfDescription": None,  # CF가 채움
            "contextNote": None,    # 컨텍스트 트랙이 채움 (혼밥·날씨 등)
        },
    }


def recommend_foods(query_text: str, top_k: int = 10) -> dict:
    """자연어 → 프론트 계약 그대로의 추천 응답. extract→match→food 객체.

    반환: {"query", "keywords", "foods": [food 객체...]}
    cfScore/contextNote는 빈 칸 — 이후 CF·컨텍스트 단계가 같은 객체를 채운다.
    """
    tags, results = recommend(query_text, top_k=top_k)
    return {
        "query": query_text,
        "keywords": tags,
        "foods": [to_food(r) for r in results],
    }


def recommend(query_text: str, top_k: int = 10) -> tuple[list[str], list[MatchResult]]:
    """자연어 한 줄 → (추출된 태그, 매칭된 메뉴 후보). 파이프라인 end-to-end.

    extract → match를 묶는다. extract가 API 키 유무로 mock/Claude 분기되는 것 외엔
    이 함수도 키와 무관.
    """
    from .extract import extract_tags

    extracted = extract_tags(query_text)
    rows = load_menu_tags()
    results = match(extracted.tags, rows, top_k=top_k)
    return extracted.tags, results


if __name__ == "__main__":
    import sys

    queries = sys.argv[1:] or ["얼큰한 국물", "혼자 가볍게", "해장되는 거", "바삭한 야식"]
    rows = load_menu_tags()
    print(f"(매칭 대상 메뉴: {len(rows)}개)\n")
    for qtext in queries:
        tags, results = recommend(qtext, top_k=8)
        print(f"■ {qtext!r}  →  추출 태그 {tags}")
        if not results:
            print("    (매칭 없음)\n")
            continue
        for r in results:
            print(
                f"    [{r.score:.3f}] store{r.store_id:<4d} {r.menu_name[:24]:24s}"
                f" 매칭{r.matched} 메뉴태그{r.tags}"
            )
        print()

    # 프론트 계약(food 객체) 출력 샘플 — 첫 쿼리
    print("=" * 60)
    print(f"프론트 계약 형태 (recommend_foods) — {queries[0]!r}")
    sample = recommend_foods(queries[0], top_k=2)
    print(json.dumps(sample, ensure_ascii=False, indent=2))
