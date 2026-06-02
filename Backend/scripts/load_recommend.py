"""LLM 산출물(jsonl) → recommend.db 적재 스크립트.

llm-tag 팀의 두 산출물을 추천 엔진용 테이블에 주입한다.
  - src/llm/data/menu_kinds.jsonl : 메뉴 → 추상 음식 종류(kind)
  - src/llm/data/menu_tags.jsonl  : 메뉴 → 태그(고정 14종)

적재 대상 (docs/db/SPEC.md 의 정적 마스터/매핑 테이블):
  - Tag         : 고정 태그 14종
  - Food        : distinct kind (food_name = kind)
  - CrawledMenu : 실제 메뉴명 → Food 매핑 (restaurant_name 은 details.db.stores 에서)
  - FoodTag     : kind ↔ 태그. 메뉴 단위 태그를 kind 단위로 집계해서 채운다.

FoodTag 집계 규칙:
  메뉴 태그는 메뉴 단위라 kind 단위로 올려야 한다.
  "한 kind 에 속한 메뉴들 중 비율 TAG_INCLUSION_RATIO 이상이 가진 태그"를
  그 kind 의 대표 태그로 채택한다. 하나도 임계치를 못 넘으면 최빈 1개만,
  많아도 MAX_TAGS_PER_KIND 개로 제한한다.

idempotent: 위 4개 테이블만 비우고 다시 채운다. User/Session/Badge 등은 건드리지 않음.

실행:
    cd Backend
    python scripts/load_recommend.py
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
from collections import Counter, defaultdict

_HERE = pathlib.Path(__file__).resolve().parent
_BACKEND = _HERE.parent
sys.path.insert(0, str(_BACKEND))

from src.data.database.schema import (  # noqa: E402
    DB_PATH,
    DETAILS_DB_PATH,
    connect,
    init_db,
)

KINDS_JSONL = _BACKEND / "src" / "llm" / "data" / "menu_kinds.jsonl"
TAGS_JSONL = _BACKEND / "src" / "llm" / "data" / "menu_tags.jsonl"

# FoodTag 집계 파라미터
TAG_INCLUSION_RATIO = 0.5   # 한 kind 의 메뉴 중 이 비율 이상이 가진 태그만 대표 태그
MAX_TAGS_PER_KIND = 6       # kind 당 대표 태그 상한


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_store_names() -> dict[int, str]:
    """details.db.stores 에서 store_id -> 식당명."""
    con = sqlite3.connect(DETAILS_DB_PATH)
    try:
        return {sid: name for sid, name in con.execute("SELECT store_id, name FROM stores")}
    finally:
        con.close()


def _aggregate_food_tags(
    menus: list[dict],
    tags_by_key: dict[tuple[int, str], list[str]],
) -> dict[str, list[str]]:
    """kind -> 대표 태그 리스트. 메뉴 단위 태그를 kind 단위로 집계."""
    menu_count: Counter[str] = Counter()
    tag_count: dict[str, Counter[str]] = defaultdict(Counter)

    for m in menus:
        kind = m["kind"]
        menu_count[kind] += 1
        for tag in tags_by_key.get((m["store_id"], m["menu_name"]), []):
            tag_count[kind][tag] += 1

    result: dict[str, list[str]] = {}
    for kind, total in menu_count.items():
        counts = tag_count[kind]
        if not counts:
            result[kind] = []
            continue
        passed = [
            (tag, n) for tag, n in counts.items() if n / total >= TAG_INCLUSION_RATIO
        ]
        if not passed:  # 임계치 미달 → 최빈 1개로 폴백
            passed = [counts.most_common(1)[0]]
        passed.sort(key=lambda x: (-x[1], x[0]))
        result[kind] = [tag for tag, _ in passed[:MAX_TAGS_PER_KIND]]
    return result


def load() -> None:
    init_db()  # 스키마 보장

    kinds_rows = _read_jsonl(KINDS_JSONL)
    tags_rows = _read_jsonl(TAGS_JSONL)
    store_names = _load_store_names()
    tags_by_key = {(r["store_id"], r["menu_name"]): r["tags"] for r in tags_rows}

    distinct_tags = sorted({t for r in tags_rows for t in r["tags"]})
    distinct_kinds = sorted({r["kind"] for r in kinds_rows})
    food_tags = _aggregate_food_tags(kinds_rows, tags_by_key)

    conn = connect()
    try:
        cur = conn.cursor()
        # 자식 → 부모 순으로 비우기 (FK 충돌 방지)
        for table in ("FoodTag", "CrawledMenu", "Food", "Tag"):
            cur.execute(f"DELETE FROM {table}")

        # Tag
        cur.executemany("INSERT INTO Tag(tag_name) VALUES (?)", [(t,) for t in distinct_tags])
        tag_id = {name: tid for tid, name in cur.execute("SELECT tag_id, tag_name FROM Tag")}

        # Food
        cur.executemany("INSERT INTO Food(food_name) VALUES (?)", [(k,) for k in distinct_kinds])
        food_id = {name: fid for fid, name in cur.execute("SELECT food_id, food_name FROM Food")}

        # FoodTag
        ft_rows = [
            (food_id[kind], tag_id[tag])
            for kind, tags in food_tags.items()
            for tag in tags
        ]
        cur.executemany("INSERT INTO FoodTag(food_id, tag_id) VALUES (?, ?)", ft_rows)

        # CrawledMenu
        cm_rows = [
            (store_names.get(m["store_id"], f"store#{m['store_id']}"), m["menu_name"], food_id[m["kind"]])
            for m in kinds_rows
        ]
        cur.executemany(
            "INSERT INTO CrawledMenu(restaurant_name, menu_name, food_id) VALUES (?, ?, ?)",
            cm_rows,
        )
        conn.commit()
    finally:
        conn.close()

    # 통계 출력
    tags_per_kind = [len(v) for v in food_tags.values()]
    avg = sum(tags_per_kind) / len(tags_per_kind) if tags_per_kind else 0
    empty = sum(1 for v in tags_per_kind if not v)
    print(f"[OK] 적재 완료 → {DB_PATH}")
    print(f"  Tag         : {len(distinct_tags)}")
    print(f"  Food        : {len(distinct_kinds)}")
    print(f"  FoodTag      : {len(ft_rows)}  (kind당 평균 {avg:.2f}태그, 태그없는 kind {empty}개)")
    print(f"  CrawledMenu : {len(cm_rows)}")


if __name__ == "__main__":
    load()
