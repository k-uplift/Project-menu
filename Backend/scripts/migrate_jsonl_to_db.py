"""LLM/크롤러 정적 자산을 recommend.db에 적재.

대상 (정적 5종):
  - Tag         (14)    SEED_TAGS
  - Food       (363+)   KINDS_BY_CATEGORY 전체 flatten + 안전망 4종
  - CrawledMenu (5,678) menu_kinds.jsonl × details.db.stores
  - FoodTag    (~1,400) menu_tags.jsonl을 kind별 집계, top 4 시드
  - Badge       (29)    Frontend/services/badges.js (수동 옮김)

동적 테이블(RecommendationSession 등)은 api wiring이 채움.
스크립트는 *idempotent* — 기존 행 모두 DELETE 후 INSERT (dev DB라 안전).

실행:
    cd Backend
    python3 scripts/migrate_jsonl_to_db.py            # 본 실행
    python3 scripts/migrate_jsonl_to_db.py --dry-run  # 개수만 보기
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Backend/scripts/ → Backend/ 추가
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.data.database.schema import DB_PATH, DETAILS_DB_PATH, init_db
from src.llm.kinds import (
    KINDS_BY_CATEGORY,
    KIND_OTHER,
    KIND_OTHER_BEVERAGE,
    KIND_OTHER_ALCOHOL,
    KIND_OTHER_SIDE,
)
from src.llm.tags import SEED_TAGS, normalize

MENU_TAGS_PATH = BACKEND_ROOT / "src" / "llm" / "data" / "menu_tags.jsonl"
MENU_KINDS_PATH = BACKEND_ROOT / "src" / "llm" / "data" / "menu_kinds.jsonl"

# Frontend/services/badges.js의 BADGES 배열을 수동으로 옮김 (1회성).
# 향후 badges.js 변경 시 여기도 갱신해야 함 — JS 파싱은 의존성 부담이 더 큼.
BADGES: list[dict] = [
    # A. 맛 속성 — 8종
    {"id": "spicy", "category": "A", "name": "칼칼함 마니아", "icon": "🌶", "description": "얼큰한 메뉴 최종 선택 5회+"},
    {"id": "soup", "category": "A", "name": "국물 애호가", "icon": "🍲", "description": "국물있는 + 한식국물탕 최종 선택 5회+"},
    {"id": "hearty", "category": "A", "name": "든든한 한 끼파", "icon": "🍚", "description": "든든한 메뉴 최종 선택 5회+"},
    {"id": "mild", "category": "A", "name": "담백 미식가", "icon": "🥗", "description": "담백한 메뉴 최종 선택 5회+"},
    {"id": "hangover", "category": "A", "name": "해장 전문가", "icon": "🍻", "description": "해장 메뉴 최종 선택 3회+ (희소 시드)"},
    {"id": "rich", "category": "A", "name": "진한 맛 추구자", "icon": "🔥", "description": "진한 메뉴 최종 선택 5회+"},
    {"id": "light", "category": "A", "name": "가벼운 한 입파", "icon": "☁️", "description": "가벼운 메뉴 최종 선택 5회+"},
    {"id": "midnight", "category": "A", "name": "야식러", "icon": "🌙", "description": "야식 메뉴를 22~02시 사이 최종 선택 3회+"},
    # B. 장르 — 6종
    {"id": "korean", "category": "B", "name": "한식 마스터", "icon": "🇰🇷", "description": "한식(국물탕/고기/면밥/조림찜) 최종 선택 10회+"},
    {"id": "japanese", "category": "B", "name": "일식 애호가", "icon": "🍣", "description": "일식 최종 선택 5회+"},
    {"id": "chinese", "category": "B", "name": "중식 탐험가", "icon": "🥟", "description": "중식 최종 선택 5회+"},
    {"id": "western", "category": "B", "name": "양식 미식가", "icon": "🍝", "description": "양식 최종 선택 5회+"},
    {"id": "chicken", "category": "B", "name": "치킨 헌터", "icon": "🍗", "description": "치킨 카테고리 최종 선택 3회+"},
    {"id": "dessert", "category": "B", "name": "디저트 러버", "icon": "🍰", "description": "디저트 최종 선택 5회+"},
    # C. 특정 음식 — 6종
    {"id": "ramen", "category": "C", "name": "라면 충신", "icon": "🍜", "description": "라면 최종 선택 3회+"},
    {"id": "tteokbokki", "category": "C", "name": "떡볶이 마니아", "icon": "🌶", "description": "떡볶이 최종 선택 3회+"},
    {"id": "meat", "category": "C", "name": "고기파", "icon": "🥩", "description": "고기류(삼겹살·갈비·스테이크 등) 최종 선택 5회+"},
    {"id": "sashimi", "category": "C", "name": "회 마니아", "icon": "🐟", "description": "회류(초밥·사시미·회덮밥 등) 최종 선택 3회+"},
    {"id": "noodle", "category": "C", "name": "면 러버", "icon": "🥢", "description": "면류(라면·우동·짜장면·파스타 등) 최종 선택 5회+"},
    {"id": "rice", "category": "C", "name": "밥심러", "icon": "🍚", "description": "밥류(비빔밥·덮밥·볶음밥 등) 최종 선택 5회+"},
    # D. 행동 패턴 — 6종
    {"id": "morning", "category": "D", "name": "아침형 인간", "icon": "🌅", "description": "6~10시 최종 선택 5회+"},
    {"id": "lunch", "category": "D", "name": "점심 인사이더", "icon": "☀️", "description": "11~14시 최종 선택 10회+"},
    {"id": "dawn", "category": "D", "name": "새벽 사냥꾼", "icon": "🌃", "description": "0~5시 검색 3회+"},
    {"id": "explorer", "category": "D", "name": "새로운 맛 탐험가", "icon": "🧭", "description": "다른 카테고리 5종 이상에서 최종 선택"},
    {"id": "regular", "category": "D", "name": "단골", "icon": "❤️", "description": "같은 식당 최종 선택 3회+"},
    {"id": "decisive", "category": "D", "name": "결정파", "icon": "🎯", "description": "검색 후 첫 추천 카드를 그대로 최종 선택 비율 70%+ (10회 이상 검색 시)"},
    # E. 메타 — 3종
    {"id": "master", "category": "E", "name": "만능 미식가", "icon": "🌟", "description": "14개 시드 중 10개 이상에서 최종 선택 1회+"},
    {"id": "specialist", "category": "E", "name": "한 우물 파", "icon": "🎭", "description": "한 시드 태그가 최종 선택의 60% 이상 점유"},
    {"id": "watcher", "category": "E", "name": "눈팅러", "icon": "👁", "description": "카드 클릭 20회+ vs 최종 선택 5회 미만 (관심↔실행 갭)"},
]


def collect_all_kinds() -> list[str]:
    """KINDS_BY_CATEGORY 전체 flatten + 4개 안전망. 중복 없이 정렬."""
    all_kinds: set[str] = set()
    for kinds in KINDS_BY_CATEGORY.values():
        all_kinds.update(kinds)
    all_kinds.update([KIND_OTHER, KIND_OTHER_BEVERAGE, KIND_OTHER_ALCOHOL, KIND_OTHER_SIDE])
    return sorted(all_kinds)


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_store_names(details_db_path: Path) -> dict[int, str]:
    """details.db.stores → {store_id: name}."""
    conn = sqlite3.connect(details_db_path)
    try:
        rows = conn.execute("SELECT store_id, name FROM stores").fetchall()
    finally:
        conn.close()
    return {sid: name for sid, name in rows}


def insert_tags(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM Tag")
    conn.executemany(
        "INSERT INTO Tag (tag_name) VALUES (?)",
        [(t,) for t in SEED_TAGS],
    )
    return len(SEED_TAGS)


def insert_foods(conn: sqlite3.Connection) -> dict[str, int]:
    """Food 적재 + {kind_name: food_id} 반환 (이후 join에 사용)."""
    conn.execute("DELETE FROM Food")
    kinds = collect_all_kinds()
    conn.executemany(
        "INSERT INTO Food (food_name) VALUES (?)",
        [(k,) for k in kinds],
    )
    rows = conn.execute("SELECT food_id, food_name FROM Food").fetchall()
    return {name: fid for fid, name in rows}


def insert_crawled_menus(
    conn: sqlite3.Connection,
    kind_to_food_id: dict[str, int],
    store_names: dict[int, str],
) -> tuple[int, int]:
    """menu_kinds.jsonl → CrawledMenu. (적재, store_id 누락) 반환."""
    conn.execute("DELETE FROM CrawledMenu")
    rows = load_jsonl(MENU_KINDS_PATH)
    inserted = 0
    missing_store = 0
    batch: list[tuple] = []
    for r in rows:
        store_id = r["store_id"]
        store_name = store_names.get(store_id)
        if store_name is None:
            missing_store += 1
            continue
        food_id = kind_to_food_id.get(r["kind"])
        # food_id 못 찾는 경우 (vocab 외 kind — 거의 없음) NULL로 INSERT
        batch.append((store_name, r["menu_name"], food_id))
        inserted += 1
    conn.executemany(
        "INSERT INTO CrawledMenu (restaurant_name, menu_name, food_id) VALUES (?, ?, ?)",
        batch,
    )
    return inserted, missing_store


def insert_food_tags(
    conn: sqlite3.Connection,
    kind_to_food_id: dict[str, int],
) -> int:
    """menu_tags.jsonl을 kind별로 집계해 top 4 시드 → FoodTag."""
    conn.execute("DELETE FROM FoodTag")
    tag_rows = conn.execute("SELECT tag_id, tag_name FROM Tag").fetchall()
    tag_name_to_id = {name: tid for tid, name in tag_rows}

    # kind ↔ menu join — menu_tags와 menu_kinds 둘 다 같은 (store_id, menu_name) 키
    menu_tags = load_jsonl(MENU_TAGS_PATH)
    menu_kinds = load_jsonl(MENU_KINDS_PATH)
    kind_by_key: dict[tuple, str] = {(m["store_id"], m["menu_name"]): m["kind"] for m in menu_kinds}

    kind_tag_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for m in menu_tags:
        key = (m["store_id"], m["menu_name"])
        kind = kind_by_key.get(key)
        if not kind:
            continue
        for raw_tag in m.get("tags", []):
            tag = normalize(raw_tag)
            if tag in tag_name_to_id:
                kind_tag_counts[kind][tag] += 1

    # top 4 tags per kind → FoodTag (idempotent: 중복 PK 무시)
    batch: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for kind, counts in kind_tag_counts.items():
        food_id = kind_to_food_id.get(kind)
        if food_id is None:
            continue
        for tag, _ in counts.most_common(4):
            tag_id = tag_name_to_id[tag]
            pair = (food_id, tag_id)
            if pair in seen:
                continue
            seen.add(pair)
            batch.append(pair)
    conn.executemany(
        "INSERT INTO FoodTag (food_id, tag_id) VALUES (?, ?)",
        batch,
    )
    return len(batch)


def insert_badges(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM Badge")
    conn.executemany(
        "INSERT INTO Badge (badge_id, category, name, icon, description) VALUES (?, ?, ?, ?, ?)",
        [(b["id"], b["category"], b["name"], b["icon"], b["description"]) for b in BADGES],
    )
    return len(BADGES)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="개수만 추정, 실제 INSERT 안 함")
    args = parser.parse_args()

    if not MENU_TAGS_PATH.exists() or not MENU_KINDS_PATH.exists():
        print(f"[X] JSONL 데이터 없음: {MENU_TAGS_PATH} / {MENU_KINDS_PATH}")
        sys.exit(1)
    if not DETAILS_DB_PATH.exists():
        print(f"[X] details.db 없음: {DETAILS_DB_PATH}")
        sys.exit(1)

    init_db()
    store_names = load_store_names(DETAILS_DB_PATH)
    print(f"[INFO] details.db stores: {len(store_names)}")

    all_kinds = collect_all_kinds()
    print(f"[INFO] 총 kind 후보: {len(all_kinds)}")

    if args.dry_run:
        menu_kinds = load_jsonl(MENU_KINDS_PATH)
        menu_tags = load_jsonl(MENU_TAGS_PATH)
        print(f"[DRY] menu_kinds.jsonl: {len(menu_kinds)}")
        print(f"[DRY] menu_tags.jsonl:  {len(menu_tags)}")
        print(f"[DRY] Tag 적재 예정:    {len(SEED_TAGS)}")
        print(f"[DRY] Food 적재 예정:   {len(all_kinds)}")
        print(f"[DRY] Badge 적재 예정:  {len(BADGES)}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        n_tag = insert_tags(conn)
        kind_to_food_id = insert_foods(conn)
        n_food = len(kind_to_food_id)
        n_crawled, n_missing = insert_crawled_menus(conn, kind_to_food_id, store_names)
        n_foodtag = insert_food_tags(conn, kind_to_food_id)
        n_badge = insert_badges(conn)
        conn.commit()
    finally:
        conn.close()

    print()
    print(f"[OK] Tag         {n_tag}")
    print(f"[OK] Food        {n_food}")
    print(f"[OK] CrawledMenu {n_crawled}  (store_id 누락 무시: {n_missing})")
    print(f"[OK] FoodTag     {n_foodtag}")
    print(f"[OK] Badge       {n_badge}")
    print(f"\n→ {DB_PATH}")


if __name__ == "__main__":
    main()
