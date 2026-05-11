"""가게 이름 → 네이버 place_id 검색 (Playwright 기반).

전략: 실제 브라우저로 https://map.naver.com/p/search/{query} 를 열고,
JS 가 호출하는 allSearch API 응답을 가로채서 JSON 을 파싱한다.
이렇게 하면 캡차/봇 탐지를 우회하면서도 우리가 원하는 raw 데이터를 얻는다.

디버그: DEBUG=1 환경변수 또는 verbose=True
응답 덤프: src/crawler/_debug/{query}__search.json
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from playwright.sync_api import Page, TimeoutError as PWTimeout

SEARCH_URL_TEMPLATE = "https://map.naver.com/p/search/{query}"
API_PATH_FRAGMENT = "/api/search/allSearch"

NAVIGATION_TIMEOUT = 20_000   # ms
RESPONSE_TIMEOUT = 15_000     # ms
THROTTLE = 1.0

DEBUG_DIR = Path(__file__).resolve().parent / "_debug"


class PlaceCandidate(dict):
    """검색 결과 한 건. 'id', 'name', 'address' 등을 포함."""


def _debug_enabled(verbose: Optional[bool]) -> bool:
    if verbose is not None:
        return verbose
    return bool(os.environ.get("DEBUG"))


def _save_dump(query: str, data: dict) -> Path:
    DEBUG_DIR.mkdir(exist_ok=True)
    safe_q = "".join(c if c.isalnum() else "_" for c in query)[:40]
    path = DEBUG_DIR / f"{safe_q}__search.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _extract_candidates(parsed: dict, debug: bool) -> list[PlaceCandidate]:
    """allSearch 응답에서 후보 리스트 추출. result.place.list 가 우선."""
    out: list[PlaceCandidate] = []

    def _candidate_from(it: dict) -> Optional[PlaceCandidate]:
        pid = it.get("id") or it.get("placeId") or it.get("entryId")
        name = it.get("name") or it.get("title")
        if not pid or not name:
            return None
        if isinstance(name, str):
            name = name.replace("<b>", "").replace("</b>", "")
        # 네이버 좌표 (WGS84): x=경도, y=위도
        try:
            lng = float(it.get("x")) if it.get("x") not in (None, "") else None
        except (TypeError, ValueError):
            lng = None
        try:
            lat = float(it.get("y")) if it.get("y") not in (None, "") else None
        except (TypeError, ValueError):
            lat = None
        return PlaceCandidate(
            id=str(pid),
            name=str(name),
            address=str(it.get("address") or it.get("addr") or ""),
            road_address=str(it.get("roadAddress") or it.get("roadAddr") or ""),
            category=str(it.get("category") or ""),
            lng=lng,
            lat=lat,
            tel=str(it.get("tel") or it.get("telDisplay") or ""),
        )

    candidate_lists: list[tuple[str, list]] = []
    result = parsed.get("result")
    if isinstance(result, dict):
        for k in ("place", "site", "all"):
            sub = result.get(k)
            if isinstance(sub, dict) and isinstance(sub.get("list"), list):
                candidate_lists.append((f'result.{k}.list', sub["list"]))

    if debug:
        print(f"  [DEBUG] JSON 최상위 키: {list(parsed.keys())}")
        if not candidate_lists:
            meta = (result or {}).get("metaInfo") if isinstance(result, dict) else None
            print(f"  [DEBUG] list 경로 없음. metaInfo={meta}")

    for path, lst in candidate_lists:
        if debug:
            print(f"  [DEBUG] {path} 길이={len(lst)}")
        for it in lst:
            if not isinstance(it, dict):
                continue
            c = _candidate_from(it)
            if c:
                out.append(c)
        if out:
            break

    return out


def search_place(
    query: str,
    page: Page,
    verbose: Optional[bool] = None,
) -> list[PlaceCandidate]:
    """검색 페이지를 열고 allSearch API 응답을 가로채서 후보 리스트 반환.

    page: browser_session() 으로 받은 Playwright Page.
    """
    debug = _debug_enabled(verbose)
    captured: list[dict] = []

    def _on_response(resp):
        if API_PATH_FRAGMENT in resp.url:
            try:
                data = resp.json()
                captured.append(data)
                if debug:
                    print(f"  [DEBUG] 응답 캡처 url={resp.url[:120]}  status={resp.status}")
            except Exception as e:
                if debug:
                    print(f"  [DEBUG] 응답 JSON 파싱 실패 url={resp.url[:80]}: {e}")

    page.on("response", _on_response)
    try:
        url = SEARCH_URL_TEMPLATE.format(query=quote(query))
        if debug:
            print(f"  [DEBUG] navigate {url}")
        try:
            page.goto(url, timeout=NAVIGATION_TIMEOUT, wait_until="domcontentloaded")
        except PWTimeout:
            if debug:
                print(f"  [DEBUG] navigation 타임아웃 (계속 진행)")

        # API 응답이 도착할 때까지 잠깐 대기
        deadline = time.time() + RESPONSE_TIMEOUT / 1000
        while not captured and time.time() < deadline:
            page.wait_for_timeout(200)
    finally:
        page.remove_listener("response", _on_response)

    if not captured:
        if debug:
            print(f"  [DEBUG] allSearch 응답을 받지 못함")
        return []

    # 보통 첫 응답이 우리가 원하는 결과
    parsed = captured[0]
    if debug:
        dump_path = _save_dump(query, parsed)
        print(f"  [DEBUG] dump → {dump_path}")

    return _extract_candidates(parsed, debug)


import re as _re

_DONG_RE = _re.compile(r"^[가-힣]+동(?:\d+가)?$")
_DONG_BASE_RE = _re.compile(r"^([가-힣]+동)\d+가$")
_ROAD_RE = _re.compile(r"^[가-힣A-Za-z0-9]+로(?:\d+(?:번)?길)?$")
_ROAD_BASE_RE = _re.compile(r"^(.+로)\d+(?:번)?길$")

# 가게명에서 무시할 흔한 접미사 (분점·본점은 매칭 시 핵심 토큰이 아님)
_NAME_SUFFIXES = {
    "본점", "분점", "지점", "직영", "직영점", "본관",
    "1호점", "2호점", "3호점", "4호점", "5호점", "6호점",
}


def _strip_brackets(addr: str) -> str:
    """주소의 괄호·쉼표를 공백으로 치환. '(삼선동4가)' 같은 토큰을 정상 분리."""
    return _re.sub(r"[(),]", " ", addr)


def _extract_location(addr: str) -> tuple[str, str]:
    """주소 문자열에서 (구, 동) 토큰 추출. 없으면 ('', '').

    예:
      '서울특별시 성북구 삼선동5가 296'              → ('성북구', '삼선동5가')
      '서울특별시 성북구 보문로 181, 1층 (삼선동4가)' → ('성북구', '삼선동4가')
    """
    if not addr:
        return ("", "")
    tokens = _strip_brackets(addr).split()
    gu = next((t for t in tokens if t.endswith("구")), "")
    dong = next((t for t in tokens if _DONG_RE.match(t)), "")
    return (gu, dong)


def _has_dong_token(addr: str) -> bool:
    """주소에 동 형태 토큰이 들어있는지. 네이버 도로명 주소는 동 없는 경우가 많음."""
    return any(_DONG_RE.match(t) for t in _strip_brackets(addr).split())


def _extract_road(addr: str) -> str:
    """주소의 도로명 베이스 토큰. 예: '삼선교로14길' → '삼선교로'.

    못 찾으면 빈 문자열.
    """
    if not addr:
        return ""
    tokens = _strip_brackets(addr).split()
    full = next((t for t in tokens if _ROAD_RE.match(t)), "")
    if not full:
        return ""
    m = _ROAD_BASE_RE.match(full)
    return m.group(1) if m else full


def _matches_location(
    cand_addr: str,
    src_gu: str,
    src_dong: str,
    src_road_base: str = "",
) -> bool:
    """후보 주소가 소스 위치와 일치하는지 검증.

    검증 순서:
      1) 구 일치 필수
      2) cand 에 동 토큰이 있으면 동까지 일치 필요
      3) cand 가 도로명 주소(동 토큰 없음)면 도로명 베이스 일치 필요
         예: source '삼선교로14길' → cand '...삼선교로 ...' 통과,
                                    cand '...동소문로 ...' 거부
    """
    if not src_gu:
        return True
    if src_gu not in cand_addr:
        return False

    if _has_dong_token(cand_addr):
        # cand 가 동 토큰을 가지고 있으면 동 일치 검사
        if not src_dong:
            return True
        if src_dong in cand_addr:
            return True
        m = _DONG_BASE_RE.match(src_dong)
        return bool(m and m.group(1) in cand_addr)

    # cand 가 도로명 주소 (동 토큰 없음) — 도로명 베이스로 검증
    if src_road_base:
        return src_road_base in cand_addr
    # 도로명 베이스도 없으면 구 매칭으로 통과 (현행 유지)
    return True


def _norm_name(s: str) -> str:
    """공백 제거 + 소문자. 비교용 정규화."""
    return _re.sub(r"\s+", "", s or "").lower()


def _name_matches(source: str, cand: str) -> bool:
    """source 의 핵심 토큰이 모두 cand 에 들어있어야 매칭 인정.

    - 흔한 접미사(본점/분점/...)는 핵심에서 제외
    - '푸른농장 정육식당' vs '푸른농장 성신여대1호점' → '정육식당' 누락 → False
    - '양슐랭 본점' vs '양슐랭 성신여대점' → 핵심 ['양슐랭'] 만 비교 → True
    - '동궁찜닭' vs '동궁찜닭 성북석관점' → True
    """
    src_n = _norm_name(source)
    cand_n = _norm_name(cand)
    if not src_n or not cand_n:
        return False
    if src_n == cand_n:
        return True
    core_tokens = [t for t in source.split() if t and t not in _NAME_SUFFIXES]
    if not core_tokens:
        return src_n in cand_n or cand_n in src_n
    return all(_norm_name(t) in cand_n for t in core_tokens)


COORD_DISTANCE_THRESHOLD_M = 300  # 좌표 일치 임계 — 300m


def find_place_id(
    name: str,
    page: Page,
    source_address: str = "",
    source_lnglat: Optional[tuple[float, float]] = None,
    verbose: Optional[bool] = None,
) -> Optional[PlaceCandidate]:
    """가장 일치도 높은 후보 1건 반환. 없으면 None.

    위치 검증 우선순위:
      A) source_lnglat 가 있고 cand 도 좌표 있으면 → 거리 300m 이내 필터 (정확)
      B) 그 외엔 source_address 의 (구, 동) 토큰 일치 필터 (텍스트)

    이름 매칭: 핵심 토큰이 모두 cand 에 포함되어야 매칭. 미일치 시 None.
    """
    try:
        candidates = search_place(name, page=page, verbose=verbose)
    except Exception as e:
        print(f"  [검색 실패] {name}: {e}")
        return None

    if not candidates:
        return None

    # === 위치 필터 ===
    if source_lnglat is not None:
        from coord import haversine_m
        src_lng, src_lat = source_lnglat
        scored: list[tuple[float, PlaceCandidate]] = []
        for c in candidates:
            if c.get("lng") is None or c.get("lat") is None:
                continue
            d = haversine_m(src_lng, src_lat, c["lng"], c["lat"])
            if d <= COORD_DISTANCE_THRESHOLD_M:
                scored.append((d, c))
        scored.sort(key=lambda x: x[0])
        validated = [c for _, c in scored]
        if verbose:
            print(f"  [DEBUG] 좌표필터 — {len(validated)}/{len(candidates)} 통과 "
                  f"(임계 {COORD_DISTANCE_THRESHOLD_M}m)")
            for d, c in scored[:3]:
                print(f"    {d:6.0f}m  {c['name']}  ({c.get('road_address') or c.get('address')})")
        if not validated:
            print(f"  [위치 불일치] {len(candidates)}개 후보 모두 좌표 {COORD_DISTANCE_THRESHOLD_M}m 밖")
            return None
        candidates = validated

    elif source_address:
        src_gu, src_dong = _extract_location(source_address)
        src_road = _extract_road(source_address)
        validated2: list[PlaceCandidate] = []
        for c in candidates:
            cand_addr = c.get("road_address") or c.get("address") or ""
            if _matches_location(cand_addr, src_gu, src_dong, src_road):
                validated2.append(c)

        if verbose:
            print(f"  [DEBUG] 주소필터 src=({src_gu}, {src_dong}, road={src_road}) — "
                  f"{len(validated2)}/{len(candidates)} 통과")

        if not validated2:
            print(f"  [위치 불일치] {len(candidates)}개 후보 모두 다른 지역")
            return None
        candidates = validated2

    # === 이름 매칭 — 핵심 토큰 모두 일치하는 첫 후보. 0건이면 None ===
    for c in candidates:
        if _norm_name(c["name"]) == _norm_name(name):
            return c
    for c in candidates:
        if _name_matches(name, c["name"]):
            return c
    if verbose:
        print(f"  [DEBUG] 이름 일치 후보 0건 (위치 통과 {len(candidates)}개) → 매칭 폐기")
    return None


if __name__ == "__main__":
    import sys
    from browser import browser_session

    q = sys.argv[1] if len(sys.argv) > 1 else "스타벅스 성신여대입구역점"
    print(f"검색어: {q}")
    print("=" * 60)
    with browser_session() as page:
        cands = search_place(q, page=page, verbose=True)
        print("=" * 60)
        print(f"\n[결과] 후보 {len(cands)}건")
        for c in cands[:5]:
            print(f"  - id={c['id']:>10}  {c['name']}  ({c.get('road_address') or c.get('address')})")
    time.sleep(THROTTLE)
    input("\n계속하려면 Enter 키를 누르세요...")
