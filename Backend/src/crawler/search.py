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
        return PlaceCandidate(
            id=str(pid),
            name=str(name),
            address=str(it.get("address") or it.get("addr") or ""),
            road_address=str(it.get("roadAddress") or it.get("roadAddr") or ""),
            category=str(it.get("category") or ""),
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


_DONG_RE = __import__("re").compile(r"^[가-힣]+동(?:\d+가)?$")


def _extract_location(addr: str) -> tuple[str, str]:
    """주소 문자열에서 (구, 동) 토큰 추출. 없으면 ('', '').

    예:
      '서울특별시 성북구 삼선동5가 296' → ('성북구', '삼선동5가')
      '서울 강북구 수유동 168-5'        → ('강북구', '수유동')
    """
    if not addr:
        return ("", "")
    tokens = addr.split()
    gu = next((t for t in tokens if t.endswith("구")), "")
    dong = next((t for t in tokens if _DONG_RE.match(t)), "")
    return (gu, dong)


def _matches_location(cand_addr: str, src_gu: str, src_dong: str) -> bool:
    """후보 주소가 소스의 (구, 동) 과 같은 위치에 있는지 검증."""
    if not src_gu:
        return True  # 비교 기준 없음 → 통과
    if src_gu not in cand_addr:
        return False
    if not src_dong:
        return True  # 구만으로도 충분
    if src_dong in cand_addr:
        return True
    # '삼선동5가' 가 후보엔 '삼선동' 으로만 있는 케이스 허용
    import re
    m = re.match(r"^([가-힣]+동)\d+가$", src_dong)
    return bool(m and m.group(1) in cand_addr)


def find_place_id(
    name: str,
    page: Page,
    source_address: str = "",
    verbose: Optional[bool] = None,
) -> Optional[PlaceCandidate]:
    """가장 일치도 높은 후보 1건 반환. 없으면 None.

    위치 검증: source_address 가 주어지면 같은 (구, 동) 인 후보만 사용.
    위치 일치 후보가 0이면 None (잘못된 가게 저장 방지).

    매칭 우선순위 (위치 일치 후보 안에서):
      1) 정확 일치
      2) 결과 name 에 BPLCNM 이 포함됨
      3) 첫 결과
    """
    try:
        candidates = search_place(name, page=page, verbose=verbose)
    except Exception as e:
        print(f"  [검색 실패] {name}: {e}")
        return None

    if not candidates:
        return None

    if source_address:
        src_gu, src_dong = _extract_location(source_address)
        validated: list[PlaceCandidate] = []
        for c in candidates:
            cand_addr = c.get("road_address") or c.get("address") or ""
            if _matches_location(cand_addr, src_gu, src_dong):
                validated.append(c)

        if verbose:
            print(f"  [DEBUG] 위치필터 src=({src_gu}, {src_dong}) — "
                  f"{len(validated)}/{len(candidates)} 통과")

        if not validated:
            print(f"  [위치 불일치] {len(candidates)}개 후보 모두 다른 지역")
            return None
        candidates = validated

    for c in candidates:
        if c["name"] == name:
            return c
    for c in candidates:
        if name in c["name"]:
            return c
    return candidates[0]


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
