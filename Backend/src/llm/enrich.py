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
    "드링크", "라테", "아이스티", "밀크티", "버블티", "식혜", "수정과",
    "카페", "모카", "프라푸", "콜드브루", "에스프", "마키아", "아포가",
    # 영어 음료명 (소문자 비교) — "티"는 스파게티니 등과 충돌하므로 단독 사용 금지
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
    # 단맛/단짠/디저트 계열 (달달한) — 5/24 데이터 점검 추가
    ("양념치킨", ("달달한", "얼큰한")),
    ("양념갈비", ("달달한", "진한")),
    ("양념게장", ("달달한", "얼큰한")),
    ("데리야", ("달달한", "진한")),
    ("깐풍", ("달달한", "얼큰한")),
    ("꿀콤보", ("달달한", "바삭한")),
    ("허니콤보", ("달달한", "바삭한")),
    ("팥빙수", ("달달한", "시원한")),
    ("빙수", ("달달한", "시원한")),
    ("아이스크림", ("달달한", "시원한")),
    ("단팥", ("달달한",)),
    ("케이크", ("달달한",)),
    ("와플", ("달달한",)),
    ("크로플", ("달달한", "바삭한")),
    ("푸딩", ("달달한",)),
    ("마카롱", ("달달한",)),
    ("쿠키", ("달달한",)),
    ("스콘", ("달달한",)),
    ("크렘", ("달달한",)),
    ("티라미", ("달달한",)),
    ("마들렌", ("달달한",)),
    ("휘낭시", ("달달한",)),
    ("누텔라", ("달달한",)),
    ("초코", ("달달한",)),
    # 치즈/크림/리치 계열 (고소한)
    ("까르보", ("고소한", "진한")),
    ("크림", ("고소한", "진한")),
    ("로제", ("고소한", "진한")),
    ("그라탕", ("고소한", "진한")),
    ("그라탱", ("고소한", "진한")),
    ("리조", ("고소한", "진한")),
    ("치즈", ("고소한", "진한")),
    ("버터", ("고소한",)),
    ("피자", ("고소한", "든든한")),
    # 튀김/바삭 계열
    ("탕수육", ("바삭한", "달달한", "진한")),
    ("돈까스", ("바삭한", "든든한")),
    ("까스", ("바삭한",)),
    ("후라이드", ("바삭한", "야식")),
    ("프라이드", ("바삭한", "야식")),
    ("가라아게", ("바삭한",)),
    ("튀김", ("바삭한",)),
    ("강정", ("달달한", "바삭한", "쫄깃한")),
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
    ("탕수", ("바삭한", "달달한", "진한")),
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
    # 추가 휴리스틱 (5/22 데이터 점검 — 안 잡힌 메뉴명 토큰 빈도 기반)
    ("치킨", ("바삭한", "야식")),
    ("버거", ("든든한", "야식")),
    ("포케", ("가벼운", "담백한")),
    ("베이글", ("가벼운", "담백한")),
    ("샌드", ("가벼운",)),          # 샌드위치
    ("요거", ("가벼운", "시원한")),  # 그릭요거트류
    ("연어", ("담백한", "시원한")),
    ("계란찜", ("담백한", "따뜻한")),
    ("계란말", ("담백한",)),
    ("김치찜", ("얼큰한", "든든한")),
    ("두부", ("담백한",)),
    ("수육", ("담백한", "든든한")),
    ("항정", ("든든한", "진한")),
    ("한우", ("든든한", "진한")),
    ("비프", ("든든한", "진한")),
    ("돼지", ("든든한", "진한")),
    ("오징어", ("쫄깃한",)),
    ("새우", ("담백한",)),
    ("골뱅이", ("얼큰한", "야식")),
    ("무침", ("얼큰한",)),          # 골뱅이·오징어·코다리무침 등 대체로 매콤
    ("조림", ("진한",)),            # 갈치·코다리·장조림 등
)

# 오매칭 차단: 메뉴명에 blocker가 있으면 해당 태그를 후보에서 제외한다.
# substring 매칭의 함정 교정 (예: '탕수육'의 '탕'이 국물 규칙에 잘못 걸림).
EXCLUSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("탕수", ("국물있는", "따뜻한")),  # 탕수육은 국물 요리가 아님
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
    "패스트푸드": ("야식", "든든한"),
    "경양식": ("든든한",),
}

MAX_TAGS = 3

# Claude enrichment 프롬프트 — 메뉴명+업종 → 시드 태그 1~3개.
ENRICH_SYSTEM_PROMPT = """\
당신은 한국 음식점 메뉴에 '먹는 경험' 태그를 붙이는 분류기입니다.
메뉴 이름(과 업종)을 보고 아래 시드 어휘에서만 1~3개를 고르세요.

시드 어휘: {seed}

규칙:
- 메뉴의 맛/온도/포만감/상황을 가장 잘 나타내는 태그를 고릅니다.
- 음료·주류·디저트 등 '맛 태그가 무의미한 비식사류'는 빈 배열을 반환합니다.
- 애매하면 더 적게 고릅니다(억지로 3개를 채우지 않음).

출력은 JSON 한 줄만: {{"tags": ["...", "..."]}}\
""".format(seed=list(SEED_TAGS))

# 구조화 출력 스키마 — 시드 어휘로만 제한(enum) → LLM이 임의 태그를 못 만든다.
ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {"type": "string", "enum": list(SEED_TAGS)},
        },
    },
    "required": ["tags"],
    "additionalProperties": False,
}


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

    # 오매칭 차단 태그 — 후보에 아예 안 넣어 MAX 캡에 좋은 태그가 밀리지 않게 한다.
    blocked: set[str] = set()
    for blocker, btags in EXCLUSIONS:
        if blocker in menu_name:
            blocked.update(btags)

    tags: list[str] = []
    for kw, kw_tags in KEYWORD_RULES:
        if kw in menu_name:
            for t in kw_tags:
                if t not in tags and t not in blocked:
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


def _user_prompt(menu_name: str, category: str | None) -> str:
    """배치/단건 공용 — 메뉴 한 건의 사용자 프롬프트."""
    cat = category or "미상"
    return f"메뉴명: {menu_name}\n업종: {cat}"


def _enrich_claude(menu_name: str, category: str | None, api_key: str) -> MenuTagResult:
    """Claude(Sonnet 4.6) 단건 호출로 메뉴 태그 부여. 실패 시 휴리스틱 폴백.

    대량(5,813건)은 scripts/enrich_menus.py의 Batches API(50% 할인)를 쓰고,
    이 단건 경로는 enrich_menu() 호출·소량 보정·디버그용이다.
    """
    try:
        import anthropic
    except ImportError:
        print("[enrich] anthropic 미설치 → 휴리스틱 폴백 (pip install anthropic)")
        return _enrich_heuristic(menu_name, category)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=128,
            system=[
                {
                    "type": "text",
                    "text": ENRICH_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": _user_prompt(menu_name, category)}],
            output_config={"format": {"type": "json_schema", "schema": ENRICH_SCHEMA}},
        )
        raw = next((b.text for b in resp.content if b.type == "text"), "")
        tags = json.loads(raw).get("tags", [])[:MAX_TAGS]
        return MenuTagResult(0, menu_name, category, list(tags), "claude")
    except Exception as e:
        print(f"[enrich] Claude 호출 실패({type(e).__name__}) → 휴리스틱 폴백")
        return _enrich_heuristic(menu_name, category)


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
    """전체 enrichment 실행 → menu_tags.jsonl 작성. 통계 dict 반환.

    주의: 이 함수는 API 키 유무와 무관하게 **항상 휴리스틱**으로 태깅한다.
    Claude로 전체를 재태깅하려면 scripts/enrich_menus.py(Batches, 50% 할인)를 쓸 것.
    (단건 Claude 보정은 enrich_menu()를 사용.)
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        print(
            "[enrich.run] 휴리스틱으로 태깅합니다 (키가 있어도). "
            "Claude 전체 재태깅은 → python scripts/enrich_menus.py"
        )
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
