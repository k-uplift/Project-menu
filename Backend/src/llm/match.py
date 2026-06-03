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

from .kinds import (
    KIND_OTHER,
    KIND_OTHER_ALCOHOL,
    KIND_OTHER_BEVERAGE,
    KIND_OTHER_SIDE,
    KIND_TO_FOOD_ID,
)
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
    price: str | None = None  # details.db.menus.price (원본 문자열)


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
    price: str | None = None  # details.db.menus.price 원본 문자열

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
    representative_tags: list[str]  # 종류 대표 태그 — 안쪽 메뉴들의 태그 빈도 top N


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


# kind 대표 태그 — *전체 메뉴* 빈도 기반. aggregate_kinds의 rep_tags가 매칭된
# 메뉴만 보면 사용자가 '얼큰한 국물' 검색했을 때 짬뽕 카드에 '바삭한'이 끌려오는
# 등 *매칭 조건*에 따라 카드 표시 태그가 흔들리는 왜곡 발생. kind 전체 메뉴로
# 계산해야 안정 — '짬뽕'은 검색 무관하게 항상 '얼큰한·국물있는·진한·따뜻한'.
_KIND_REP_TAGS_CACHE: dict[str, list[str]] | None = None

# kind 별 *전체 식당 수* (모든 메뉴 통틀어). 카드의 'X개 식당이 판매' 표시용 —
# 검색 매칭과 무관한 그 종류의 *진짜 풍부도*. 한 번 빌드 후 모듈 캐시.
_KIND_STORE_COUNT_CACHE: dict[str, int] | None = None


def _get_kind_rep_tags(rows: list[MenuRow] | None = None) -> dict[str, list[str]]:
    global _KIND_REP_TAGS_CACHE
    if _KIND_REP_TAGS_CACHE is None:
        if rows is None:
            rows = load_menu_tags()
        kind_tag_counts: dict[str, Counter[str]] = {}
        for r in rows:
            if not r.kind:
                continue
            c = kind_tag_counts.setdefault(r.kind, Counter())
            for t in r.tags:
                c[normalize(t)] += 1
        _KIND_REP_TAGS_CACHE = {
            kind: [t for t, _ in counts.most_common(4)]
            for kind, counts in kind_tag_counts.items()
        }
    return _KIND_REP_TAGS_CACHE


def _get_kind_store_count(rows: list[MenuRow] | None = None) -> dict[str, int]:
    """kind 별 distinct 식당 수 — *그 종류 전체 메뉴* 기반 (검색 무관)."""
    global _KIND_STORE_COUNT_CACHE
    if _KIND_STORE_COUNT_CACHE is None:
        if rows is None:
            rows = load_menu_tags()
        bag: dict[str, set] = {}
        for r in rows:
            if r.kind:
                bag.setdefault(r.kind, set()).add(r.store_id)
        _KIND_STORE_COUNT_CACHE = {k: len(s) for k, s in bag.items()}
    return _KIND_STORE_COUNT_CACHE


@dataclass
class StoreInfo:
    """식당 메타 — 프론트 RestaurantCard에 필요한 정보. details.db + restaurants.db join."""
    name: str | None
    address: str | None        # 지번 주소 (restaurants.SITEWHLADDR)
    road_address: str | None   # 도로명 주소 (restaurants.RDNWHLADDR) — 더 친화적
    phone: str | None          # 전화번호 (restaurants.SITETEL)
    category: str | None       # 업태명 (restaurants.UPTAENM): 한식·일식·중식 등
    hours: str | None          # 대표 영업시간 "10:00 ~ 23:00"
    closed_days: list[str]     # 휴무 요일 ["일", "월"]
    break_time: str | None     # 브레이크타임 "15:00 ~ 17:00" — 가장 흔한 break 페어
    last_order: str | None     # 라스트오더 — 요일별 다르면 "요일별 상이"
    latitude: float | None     # WGS84 위도 — restaurants.X/Y(EPSG:5181) 변환
    longitude: float | None    # WGS84 경도
    price_range: str | None    # "8,000~15,000원"
    naver_place_id: str | None # details.stores.naver_place_id — 네이버 외부 링크용


_STORE_INFO_CACHE: dict[int, StoreInfo] | None = None
DEFAULT_RESTAURANTS_DB = _HERE / ".." / ".." / "db" / "restaurants.db"


# 서울 행정데이터 좌표계 — EPSG:5181 (KATEC, 중부원점). always_xy=True로 (lon, lat) 순서.
# Transformer는 thread-safe 하고 한 번 만들면 재사용 가능 — 모듈 레벨 인스턴스.
_COORD_TRANSFORMER = None


def _coord_to_wgs84(x_str: str | None, y_str: str | None) -> tuple[float | None, float | None]:
    """restaurants.db의 X/Y 문자열(EPSG:5181) → (lat, lon) WGS84.

    빈 값·변환 실패는 (None, None). pyproj 없으면 (None, None) — 좌표 없어도 응답은 정상.
    """
    if not x_str or not y_str:
        return None, None
    try:
        x = float(x_str)
        y = float(y_str)
    except (TypeError, ValueError):
        return None, None
    global _COORD_TRANSFORMER
    if _COORD_TRANSFORMER is None:
        try:
            from pyproj import Transformer
            _COORD_TRANSFORMER = Transformer.from_crs("EPSG:5181", "EPSG:4326", always_xy=True)
        except ImportError:
            return None, None
    try:
        lon, lat = _COORD_TRANSFORMER.transform(x, y)
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


_PRICE_DIGIT_RE = re.compile(r"\d[\d,]*")


def _parse_prices(prices: list[str]) -> str | None:
    """가격 문자열 리스트 → '8,000~15,000원' 또는 None.

    DB의 price 포맷이 다양: '8000', '8,000', '22000~41000', '시가', '~12000', '8,000원'.
    각 문자열에서 숫자 시퀀스 다 뽑아 min/max 계산. 숫자 0개면 None.
    """
    nums: list[int] = []
    for p in prices:
        if not p:
            continue
        for m in _PRICE_DIGIT_RE.findall(p):
            try:
                nums.append(int(m.replace(",", "")))
            except ValueError:
                pass
    if not nums:
        return None
    lo, hi = min(nums), max(nums)
    if lo == hi:
        return f"{lo:,}원"
    return f"{lo:,}~{hi:,}원"


def _load_store_info(
    details_db: Path = DEFAULT_DETAILS_DB,
    restaurants_db: Path = DEFAULT_RESTAURANTS_DB,
) -> dict[int, StoreInfo]:
    """details.db + restaurants.db → store_id → StoreInfo 매핑. 모듈 캐시.

    enrich 결과(menu_tags.jsonl)는 LLM 태깅 산출물만 들고, 식당 메타는 source-of-truth인
    DB에서 join. 데이터 갱신되면 캐시 reset 후 재실행.
    """
    global _STORE_INFO_CACHE
    if _STORE_INFO_CACHE is not None:
        return _STORE_INFO_CACHE
    import sqlite3

    conn = sqlite3.connect(f"file:{details_db}?mode=ro", uri=True)
    try:
        try:
            conn.execute(f"ATTACH DATABASE 'file:{restaurants_db}?mode=ro' AS r KEY ''")
        except sqlite3.OperationalError:
            conn.execute(f"ATTACH DATABASE '{restaurants_db}' AS r")
        # 식당 기본 정보 — 이름·주소(지번/도로명)·전화·업태·좌표·네이버 id
        cur = conn.execute(
            """
            SELECT s.store_id, s.name, s.naver_place_id,
                   rr.SITEWHLADDR, rr.RDNWHLADDR, rr.SITETEL, rr.UPTAENM,
                   rr.X, rr.Y
            FROM stores s
            LEFT JOIN r.restaurants rr ON rr.MGTNO = s.mgtno
            """
        )
        meta = {
            int(sid): {
                "name": name,
                "naver_place_id": npid,
                "address": addr,
                "road_address": raddr,
                "phone": tel,
                "category": cat,
                "x": x,
                "y": y,
            }
            for sid, name, npid, addr, raddr, tel, cat, x, y in cur.fetchall()
        }
        # 영업시간 — 가장 흔한 open-close 페어 = 대표, is_closed=1 요일 = 휴무.
        # break_start/break_end·last_order도 같이 수집해 부가 정보 노출.
        hours_by_sid: dict[int, list[tuple]] = {}
        for sid, dow, ot, ct, closed, bs, be, lo in conn.execute(
            """SELECT store_id, day_of_week, open_time, close_time, is_closed,
                      break_start, break_end, last_order FROM business_hours"""
        ):
            hours_by_sid.setdefault(int(sid), []).append(
                (dow, ot, ct, closed, bs, be, lo)
            )
        # 식당별 가격 — priceRange 계산용
        prices_by_sid: dict[int, list[str]] = {}
        for sid, price in conn.execute(
            "SELECT store_id, price FROM menus WHERE price IS NOT NULL AND price != ''"
        ):
            prices_by_sid.setdefault(int(sid), []).append(price)
    finally:
        conn.close()

    out: dict[int, StoreInfo] = {}
    for sid, m in meta.items():
        rows = hours_by_sid.get(sid, [])
        closed = [dow for dow, _, _, c, _, _, _ in rows if c]
        open_pairs = [(ot, ct) for _, ot, ct, c, _, _, _ in rows if not c and ot and ct]
        if open_pairs:
            most = Counter(open_pairs).most_common(1)[0][0]
            hours = f"{most[0]} ~ {most[1]}"
        else:
            hours = None
        # 브레이크타임 — 가장 흔한 (break_start, break_end) 페어. 둘 다 있을 때만.
        break_pairs = [
            (bs, be) for _, _, _, c, bs, be, _ in rows if not c and bs and be
        ]
        if break_pairs:
            most_break = Counter(break_pairs).most_common(1)[0][0]
            break_time = f"{most_break[0]} ~ {most_break[1]}"
        else:
            break_time = None
        # 라스트오더 — 가장 흔한 값. 요일별 다르면 그래도 대표값.
        last_orders = [lo for _, _, _, c, _, _, lo in rows if not c and lo]
        last_order = Counter(last_orders).most_common(1)[0][0] if last_orders else None
        # 전화번호 — 공백 패딩 정리
        phone = (m["phone"] or "").strip() or None
        address = (m["address"] or "").strip() or None
        road_address = (m["road_address"] or "").strip() or None
        lat, lon = _coord_to_wgs84(m["x"], m["y"])
        price_range = _parse_prices(prices_by_sid.get(sid, []))
        out[sid] = StoreInfo(
            name=m["name"],
            address=address,
            road_address=road_address,
            phone=phone,
            category=m["category"],
            hours=hours,
            closed_days=closed,
            break_time=break_time,
            last_order=last_order,
            latitude=lat,
            longitude=lon,
            price_range=price_range,
            naver_place_id=m["naver_place_id"],
        )
    _STORE_INFO_CACHE = out
    return out


def _load_store_names(db_path: Path = DEFAULT_DETAILS_DB) -> dict[int, str]:
    """store_id → name (load_menu_tags 호환). 내부적으로 _load_store_info 위에 얹음."""
    return {sid: info.name for sid, info in _load_store_info().items() if info.name}


_MENU_PRICE_CACHE: dict[tuple[int, str], str] | None = None


def _load_menu_prices(db_path: Path = DEFAULT_DETAILS_DB) -> dict[tuple[int, str], str]:
    """(store_id, menu_name) → price (원본 문자열). 모듈 캐시.

    DB의 price는 '22000', '22000~41000', '시가' 등 다양한 포맷이라 문자열 그대로 보존.
    프론트가 표시 형태 결정.
    """
    global _MENU_PRICE_CACHE
    if _MENU_PRICE_CACHE is not None:
        return _MENU_PRICE_CACHE
    import sqlite3

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute("SELECT store_id, menu_name, price FROM menus")
        _MENU_PRICE_CACHE = {
            (int(sid), name): price for sid, name, price in cur.fetchall() if price
        }
    finally:
        conn.close()
    return _MENU_PRICE_CACHE


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

    details.db에서 store_name·price를 함께 join. menu_kinds.jsonl이 있으면 kind도 채움.
    """
    store_names = _load_store_names()
    kinds = _load_menu_kinds()
    prices = _load_menu_prices()
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
                    price=prices.get((sid, mname)),
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
        # 종류의 대표 태그 — *kind 전체 메뉴* 빈도 기반 (모듈 캐시). 매칭된 메뉴만
        # 보면 '얼큰한 국물' 검색 시 짬뽕 카드에 '바삭한'(세트 안 탕수육에서 끌려옴)
        # 같은 잡태그가 끼는 왜곡 발생. 전체 메뉴 기반은 검색 무관하게 안정.
        rep_tags = _get_kind_rep_tags().get(kind, [])
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
                representative_tags=rep_tags,
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
                price=row.price,
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
    """KindGroup → 프론트 FoodItem 계약 (foods.mock.js 형태).

    1차 응답은 *음식 이름만* 가볍게. 식당·메뉴 리스트는 사용자가 음식을 클릭한 뒤
    별도 API(recommend_stores_for_kind)로 받아온다 — 응답 크기·전송량 절감.

    id 체계: vocab 인덱스 기반 'food-001'. KIND_TO_FOOD_ID 매핑은 결정적.
    tags: 그 종류 메뉴들의 태그 빈도 top 4 (대표 태그).
    cfScore/cfDescription/contextNote: 이후 CF/컨텍스트 단계가 채울 빈 칸.
    emoji/imageUrl: 프론트 호환성 위해 null로 명시.
    """
    return {
        "id": KIND_TO_FOOD_ID.get(g.kind, f"food-{g.kind}"),
        "name": g.kind,
        "emoji": None,
        "imageUrl": None,
        "tags": g.representative_tags,
        "score": _to_score100(g.score),
        # *전체* 식당 수 — 검색 무관, 그 종류 풍부도. (g.n_stores 는 매칭된 메뉴 식당만)
        "nStores": _get_kind_store_count().get(g.kind, g.n_stores),
        "reason": {
            "matchedKeywords": g.matched,
            "matchedFoodKeywords": g.matched_food_keywords,
            "cfScore": None,
            "cfDescription": None,
            "contextNote": None,
        },
    }


@dataclass
class StoreGroup:
    """식당 단위 집계 결과 — 2차 추천 (선택된 음식 종류 안의 식당들).

    한 식당이 그 종류 메뉴를 여러 개 가져도 한 그룹으로 묶이고, 그 식당의 대표
    점수는 가장 높은 메뉴 점수. 안쪽 menus 리스트로 같은 식당의 다른 매칭 메뉴를
    같이 볼 수 있다.
    """
    store_id: int
    store_name: str | None
    score: float                 # max(메뉴 score)
    menus: list[MatchResult]     # score 내림차순. 한 식당의 매칭 메뉴들
    matched: list[str]
    matched_food_keywords: list[str]


def aggregate_stores(
    results: list[MatchResult],
    top_k: int = 10,
) -> list[StoreGroup]:
    """매칭된 메뉴들을 식당 단위로 묶는다. 한 식당이 여러 메뉴로 잡혔으면 합쳐서
    그 식당의 대표 점수(=max) 하나로 노출. CF 재랭킹·식당 카드 노출에 자연스러운 단위.
    """
    grouped: dict[int, list[MatchResult]] = {}
    for r in results:
        grouped.setdefault(r.store_id, []).append(r)

    groups: list[StoreGroup] = []
    for sid, menus in grouped.items():
        menus.sort(key=lambda m: m.score, reverse=True)
        top = menus[0]
        all_matched = sorted({t for m in menus for t in m.matched})
        all_fkw = sorted({k for m in menus for k in m.matched_food_keywords})
        groups.append(
            StoreGroup(
                store_id=sid,
                store_name=top.store_name,
                score=top.score,
                menus=menus,
                matched=all_matched,
                matched_food_keywords=all_fkw,
            )
        )

    # 점수 동률이면 매칭 메뉴 수가 많은 식당이 위로 — 그 식당이 종류와 잘 맞는다는 신호.
    groups.sort(key=lambda g: (g.score, len(g.menus)), reverse=True)
    return groups[:top_k]


def to_store_group(g: StoreGroup) -> dict:
    """StoreGroup → 프론트 Restaurant 계약 (restaurants.mock.js 형태).

    DB에서 가져올 수 있는 필드만 채운다 — id, name, address, category, hours,
    closedDay, menuItems. mock 전용 필드(rating/reviewCount/priceRange/delivery/
    signature/cfMatch)는 노출 안 함 — 프론트가 필요하면 기본값 처리.
    latitude/longitude: 원본이 한국 평면좌표(EPSG)라 변환 필요 — 일단 null.
    """
    info = _load_store_info().get(g.store_id)
    return {
        "id": f"rest-{g.store_id}",
        "storeId": g.store_id,
        "name": g.store_name,
        "address": info.address if info else None,
        "roadAddress": info.road_address if info else None,
        "phone": info.phone if info else None,
        "category": info.category if info else None,
        "latitude": info.latitude if info else None,
        "longitude": info.longitude if info else None,
        "hours": info.hours if info else None,
        "closedDay": ", ".join(info.closed_days) if info and info.closed_days else None,
        "breakTime": info.break_time if info else None,
        "lastOrder": info.last_order if info else None,
        "priceRange": info.price_range if info else None,
        "naverPlaceId": info.naver_place_id if info else None,
        "score": _to_score100(g.score),
        "reason": {
            "matchedKeywords": g.matched,
            "matchedFoodKeywords": g.matched_food_keywords,
        },
        # 그 식당의 이 종류 매칭 메뉴 — 프론트 menuItems 모양 (name/price). 우리 DB엔
        # signature 정보가 없어 isSignature는 항상 false.
        "menuItems": [
            {
                "name": m.menu_name,
                "price": m.price,
                "isSignature": False,
                "foodId": stable_food_id(m.store_id, m.menu_name),
                "tags": m.tags,
                "score": _to_score100(m.score),
            }
            for m in g.menus
        ],
    }


def recommend_foods(query_text: str, top_k: int = 10) -> dict:
    """1차 단계: 자연어 → 음식 종류 이름 리스트. 가벼운 응답.

    반환: {"query", "keywords", "excludeKeywords", "foodKeywords",
           "excludeFoodKeywords", "kinds": [{kind, score, reason}, ...]}.

    사용자가 음식을 선택하면 recommend_stores_for_kind(query, kind)를 호출해
    그 종류의 식당 리스트를 따로 받는다.
    """
    # 종류 집계용으로 메뉴를 넓게 가져온다 — 사이드/음료가 제외되니 후보 풀이 필요.
    extracted, wide_results = _recommend_extracted(query_text, top_k=top_k * 8)
    kinds = aggregate_kinds(wide_results, top_k=top_k)
    return {
        "query": query_text,
        "keywords": extracted.tags,
        "excludeKeywords": extracted.exclude_tags,
        "foodKeywords": extracted.food_keywords,
        "excludeFoodKeywords": extracted.exclude_food_keywords,
        "kinds": [to_kind_group(g) for g in kinds],
    }


def recommend_foods_by_tags(
    tags: list[str],
    top_k: int = 10,
    food_keywords: list[str] | None = None,
) -> dict:
    """사용자가 *직접 선택한 시드 태그*로 추천. extract 단계 건너뛰기.

    KeywordScreen 에서 사용자가 키워드 추가/제거 한 경우 그 결과가 그대로 매칭에
    들어가야 한다. food_keywords 는 /extract 가 *원본 자연어에서* 한 번 뽑아둔
    카테고리·식재료 신호를 그대로 전달받아 사용 (Claude 추가 호출 없음).
    exclude_* 채널은 사용자 의도에 명시되지 않아 비움.

    응답 모양은 recommend_foods() 와 동일 — 프론트 카드 컴포넌트 호환.
    """
    if not tags:
        return {
            "query": "",
            "keywords": [],
            "excludeKeywords": [],
            "foodKeywords": [],
            "excludeFoodKeywords": [],
            "kinds": [],
        }
    fkw = list(food_keywords or [])
    rows = load_menu_tags()
    wide_results = match(
        tags,
        rows,
        top_k=top_k * 8,
        exclude_tags=[],
        food_keywords=fkw,
        exclude_food_keywords=[],
    )
    kinds = aggregate_kinds(wide_results, top_k=top_k)
    return {
        "query": "",
        "keywords": list(tags),
        "excludeKeywords": [],
        "foodKeywords": fkw,
        "excludeFoodKeywords": [],
        "kinds": [to_kind_group(g) for g in kinds],
    }


def recommend_stores_for_kind(
    query_text: str, kind: str, top_k: int = 10
) -> dict:
    """2차 단계: 사용자가 음식 종류를 선택하면, 그 종류를 파는 식당들을 추천.

    같은 쿼리(태그·food_keywords·exclude)를 다시 적용해 *해당 종류 안에서* 점수화.
    이전 컨텍스트("한식 든든하게")가 살아남아 사용자 취향에 맞는 식당이 위로 온다.

    반환: {"query", "kind", "stores": [식당 객체...]}.
    프론트의 RestaurantScreen 카드 리스트로 그대로 매핑 가능.
    """
    extracted, all_results = _recommend_extracted(query_text, top_k=10**6)
    # 해당 종류 메뉴만 필터.
    filtered = [r for r in all_results if r.kind == kind]
    stores = aggregate_stores(filtered, top_k=top_k)
    return {
        "query": query_text,
        "kind": kind,
        "keywords": extracted.tags,
        "excludeKeywords": extracted.exclude_tags,
        "foodKeywords": extracted.food_keywords,
        "excludeFoodKeywords": extracted.exclude_food_keywords,
        "stores": [to_store_group(s) for s in stores],
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
        # 1차: 음식 종류 (이름만)
        kinds = aggregate_kinds(results, top_k=8)
        for g in kinds:
            print(f"    [{g.score:.3f}] {g.kind}")
        # 2차 데모: 상위 종류를 클릭했다 치고 그 종류의 식당 추천
        if kinds:
            picked = kinds[0].kind
            stores_resp = recommend_stores_for_kind(qtext, picked, top_k=5)
            print(f"    └ '{picked}' 클릭 시 식당:")
            for s in stores_resp["stores"]:
                top_menu = s["menuItems"][0]["name"][:24] if s["menuItems"] else ""
                print(
                    f"        [{s['score']:3d}] {(s['name'] or '?')[:20]:20s}"
                    f"  대표: {top_menu}"
                )
        print()

    # 프론트 계약(food 객체) 출력 샘플 — 첫 쿼리
    print("=" * 60)
    print(f"프론트 계약 형태 (recommend_foods) — {queries[0]!r}")
    sample = recommend_foods(queries[0], top_k=2)
    print(json.dumps(sample, ensure_ascii=False, indent=2))
