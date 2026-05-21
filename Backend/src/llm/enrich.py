"""메뉴 태그 enrichment — 메뉴명 + 업종 → 시드 태그.

5/17 회의 확정 파이프라인의 매칭 단계 준비물.
쿼리에서 태그는 extract.py로 뽑지만, 매칭할 메뉴 쪽 태그가 없으면 추천이 끊긴다.
이 모듈이 메뉴 5,813행(중복 가격행 제외 distinct 요리 ≈5,678개)에 시드 태그를 부여한다.

설계:
- 공유 details.db는 **읽기 전용**. DB팀 크롤러가 계속 재생성하므로 직접 수정 금지.
- 출력은 별도 텍스트 파일 menu_tags.jsonl — git 친화(text diff) + 사용자 spot-check용.
- details.db가 바뀌면 그냥 다시 돌리면 된다 (재실행 가능, 결정적).
- ANTHROPIC_API_KEY 있으면 Claude, 없으면 휴리스틱 — extract.py와 동일 분기 패턴.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .tags import SEED_TAGS

CLAUDE_MODEL = "claude-sonnet-4-6"

# 모듈 기준 경로 (Backend/src/llm/)
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent.parent  # Backend/
DEFAULT_DETAILS_DB = _BACKEND / "db" / "details.db"
DEFAULT_RESTAURANTS_DB = _BACKEND / "db" / "restaurants.db"
DEFAULT_OUT = _HERE / "data" / "menu_tags.jsonl"

# 음료/주류/비음식 — 맛 태그를 붙이지 않는다 (source="drink").
DRINK_MARKERS: tuple[str, ...] = (
    "사이다", "콜라", "펩시", "사프", "스프라이트", "환타", "에이드", "토닉",
    "커피", "라떼", "아메리카노", "에스프레소", "카푸치노", "프라페", "스무디",
    "쉐이크", "쥬스", "주스", "음료", "탄산", "맥주", "생맥", "소주", "하이볼",
    "와인", "막걸리", "사케", "위스키", "보드카", "칵테일", "차(", "녹차", "홍차",
    "드링크", "라테",
    # 영어 음료명 (소문자 비교)
    "latte", "americano", "cappuccino", "espresso", "ade", "cola",
    "juice", "beer", "coffee", "smoothie",
)

# 메뉴명 키워드 → 시드 태그. 구체적인 것을 위에 둔다 (먼저 매칭되면 우선).
# 출력은 SEED_TAGS 범위로 제한해 매칭을 깔끔하게 유지한다.
KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # 해장 계열 (국물+해장 둘 다)
    ("해장", ("해장", "국물있는")),
    ("선지", ("해장", "국물있는")),
    ("내장탕", ("해장", "국물있는")),
    ("콩나물국밥", ("해장", "국물있는")),
    ("술국", ("해장", "국물있는", "야식")),
    # 국물 계열
    ("찌개", ("국물있는", "따뜻한")),
    ("전골", ("국물있는", "따뜻한", "든든한")),
    ("국밥", ("국물있는", "따뜻한", "든든한")),
    ("지리", ("국물있는", "담백한")),
    ("매운탕", ("국물있는", "얼큰한")),
    ("짬뽕", ("국물있는", "얼큰한")),
    ("라면", ("국물있는", "얼큰한")),
    ("우동", ("국물있는", "담백한")),
    ("쌀국수", ("국물있는", "담백한")),
    ("칼국수", ("국물있는", "따뜻한")),
    ("탕", ("국물있는", "따뜻한")),
    ("국", ("국물있는", "따뜻한")),
    # 매운 계열
    ("불닭", ("얼큰한", "야식")),
    ("마라", ("얼큰한", "진한")),
    ("매운", ("얼큰한",)),
    ("매콤", ("얼큰한",)),
    ("청양", ("얼큰한",)),
    ("불", ("얼큰한",)),
    ("아구찜", ("얼큰한", "쫄깃한")),
    ("떡볶이", ("얼큰한", "쫄깃한")),
    # 튀김/바삭 계열
    ("탕수육", ("바삭한", "진한")),
    ("돈까스", ("바삭한", "든든한")),
    ("까스", ("바삭한",)),
    ("후라이드", ("바삭한", "야식")),
    ("프라이드", ("바삭한", "야식")),
    ("가라아게", ("바삭한",)),
    ("튀김", ("바삭한",)),
    ("강정", ("바삭한", "쫄깃한")),
    # 찜/고기 계열 (든든+진한)
    ("찜닭", ("든든한", "진한")),
    ("갈비찜", ("든든한", "진한")),
    ("족발", ("든든한", "쫄깃한")),
    ("보쌈", ("든든한", "담백한")),
    ("삼겹", ("든든한", "진한")),
    ("목살", ("든든한",)),
    ("갈비", ("든든한", "진한")),
    ("스테이크", ("든든한", "진한")),
    ("곱창", ("진한", "야식")),
    ("대창", ("진한", "야식")),
    ("막창", ("진한", "야식")),
    ("제육", ("든든한", "얼큰한")),
    ("불고기", ("든든한", "진한")),
    ("구이", ("든든한", "진한")),
    ("육회", ("쫄깃한", "담백한")),
    # 회/일식 계열 (담백/시원)
    ("물회", ("시원한", "얼큰한")),
    ("회", ("담백한", "시원한")),
    ("사시미", ("담백한", "시원한")),
    ("초밥", ("담백한",)),
    ("스시", ("담백한",)),
    ("롤", ("담백한",)),
    ("냉면", ("시원한", "담백한")),
    ("냉", ("시원한",)),
    # 분식/가벼운 계열
    ("김밥", ("가벼운",)),
    ("주먹밥", ("가벼운",)),
    ("샐러드", ("가벼운", "시원한")),
    ("토스트", ("가벼운",)),
    ("샌드위치", ("가벼운",)),
    # 죽/담백 계열
    ("죽", ("담백한", "따뜻한")),
    ("백반", ("담백한", "든든한")),
    ("정식", ("든든한", "담백한")),
    # 만두/전/밥류/중식 추가
    ("꿔바로우", ("바삭한", "진한")),
    ("궈바로우", ("바삭한", "진한")),
    ("탕수", ("바삭한", "진한")),
    ("군만두", ("바삭한",)),
    ("만두", ("든든한",)),
    ("순대", ("든든한",)),
    ("파전", ("바삭한",)),
    ("해물전", ("바삭한",)),
    ("김치전", ("바삭한",)),
    ("모듬전", ("바삭한",)),
    ("빈대떡", ("바삭한",)),
    ("부침", ("바삭한",)),
    ("볶음밥", ("든든한",)),
    ("덮밥", ("든든한",)),
    ("비빔밥", ("든든한", "담백한")),
    ("카레", ("진한", "든든한")),
    ("커리", ("진한", "든든한")),
    ("쌈밥", ("든든한", "담백한")),
    # 면 (국물 키워드 미적중 시 가벼운)
    ("파스타", ("가벼운", "진한")),
    ("비빔", ("얼큰한",)),
    ("국수", ("담백한",)),
    ("면", ("담백한",)),
)

# 키워드 미적중 시 업종(UPTAENM) 기반 fallback.
CATEGORY_DEFAULTS: dict[str, tuple[str, ...]] = {
    "호프/통닭": ("야식", "바삭한"),
    "횟집": ("시원한", "담백한"),
    "분식": ("가벼운",),
    "중국식": ("진한",),
    "일식": ("담백한",),
    "정종/대포집/소주방": ("야식",),
    "식육(숯불구이)": ("든든한", "진한"),
    "까페": ("가벼운",),
}

MAX_TAGS = 3


@dataclass
class MenuTagResult:
    store_id: int
    menu_name: str
    category: str | None
    tags: list[str]
    source: str  # "claude" | "heuristic" | "drink" | "fallback"


def _is_drink(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in DRINK_MARKERS)


def _enrich_heuristic(menu_name: str, category: str | None) -> MenuTagResult:
    """규칙 기반. 메뉴명 키워드 우선, 미적중 시 업종 fallback."""
    if _is_drink(menu_name):
        return MenuTagResult(0, menu_name, category, [], "drink")

    tags: list[str] = []
    for kw, kw_tags in KEYWORD_RULES:
        if kw in menu_name:
            for t in kw_tags:
                if t not in tags:
                    tags.append(t)
            if len(tags) >= MAX_TAGS:
                break

    if tags:
        return MenuTagResult(0, menu_name, category, tags[:MAX_TAGS], "heuristic")

    # 키워드 미적중 → 업종 기본값
    if category and category in CATEGORY_DEFAULTS:
        return MenuTagResult(
            0, menu_name, category, list(CATEGORY_DEFAULTS[category])[:MAX_TAGS], "fallback"
        )
    return MenuTagResult(0, menu_name, category, [], "fallback")


def _enrich_claude(menu_name: str, category: str | None, api_key: str) -> MenuTagResult:
    raise NotImplementedError(
        "anthropic 클라이언트 미연결. API 키 수령 후 구현 — 메뉴명+업종을 주고 "
        "시드 태그 1~3개를 JSON으로 받게 한다 (extract._extract_claude와 동일 패턴)."
    )


def enrich_menu(menu_name: str, category: str | None = None) -> MenuTagResult:
    """단일 메뉴 태그 부여. API 키 있으면 Claude, 없으면 휴리스틱."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return _enrich_claude(menu_name, category, api_key)
    return _enrich_heuristic(menu_name, category)


def load_dishes(
    details_db: Path = DEFAULT_DETAILS_DB,
    restaurants_db: Path = DEFAULT_RESTAURANTS_DB,
) -> list[tuple[int, str, str | None]]:
    """distinct (store_id, menu_name, category) 목록. details.db는 읽기 전용."""
    conn = sqlite3.connect(f"file:{details_db}?mode=ro", uri=True)
    try:
        conn.execute(f"ATTACH DATABASE 'file:{restaurants_db}?mode=ro' AS r KEY ''")
    except sqlite3.OperationalError:
        # KEY 미지원 빌드 대비
        conn.execute(f"ATTACH DATABASE '{restaurants_db}' AS r")
    rows = conn.execute(
        """
        SELECT DISTINCT m.store_id, m.menu_name, rr.UPTAENM
        FROM menus m
        JOIN stores s ON s.store_id = m.store_id
        LEFT JOIN r.restaurants rr ON rr.MGTNO = s.mgtno
        ORDER BY m.store_id, m.menu_name
        """
    ).fetchall()
    conn.close()
    return [(int(sid), name, cat) for sid, name, cat in rows]


def run(out_path: Path = DEFAULT_OUT) -> dict:
    """전체 enrichment 실행 → menu_tags.jsonl 작성. 통계 dict 반환."""
    dishes = load_dishes()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    source_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    tagged = 0

    with out_path.open("w", encoding="utf-8") as f:
        for store_id, menu_name, category in dishes:
            r = _enrich_heuristic(menu_name, category)
            r.store_id = store_id
            source_counter[r.source] += 1
            if r.tags:
                tagged += 1
                tag_counter.update(r.tags)
            f.write(
                json.dumps(
                    {
                        "store_id": r.store_id,
                        "menu_name": r.menu_name,
                        "category": r.category,
                        "tags": r.tags,
                        "source": r.source,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    return {
        "total_dishes": len(dishes),
        "tagged": tagged,
        "untagged": len(dishes) - tagged,
        "coverage": round(tagged / len(dishes), 3) if dishes else 0.0,
        "by_source": dict(source_counter),
        "by_tag": dict(tag_counter.most_common()),
        "out": str(out_path),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 인자로 준 메뉴명 즉석 테스트: python -m src.llm.enrich "황금찜닭" "콩나물국밥"
        for name in sys.argv[1:]:
            r = enrich_menu(name)
            print(f"[{r.source:9s}] {name!r:30s} → {r.tags}")
    else:
        stats = run()
        print("=== 메뉴 태그 enrichment 완료 ===")
        print(f"총 요리(distinct): {stats['total_dishes']}")
        print(f"태그 부여됨: {stats['tagged']}  (커버리지 {stats['coverage']*100:.1f}%)")
        print(f"태그 없음: {stats['untagged']}")
        print(f"source별: {stats['by_source']}")
        print(f"태그 분포: {stats['by_tag']}")
        print(f"출력: {stats['out']}")
