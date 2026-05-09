"""place_id → 메뉴 / 영업시간 파싱.

네이버 플레이스는 페이지 안에 window.__APOLLO_STATE__ 로 거대한 GraphQL
캐시 dict 를 박아둔다 (SSR). 메뉴/영업시간 모두 그 안에 있다.

추출 순서 (우선순위):
  1) page.evaluate("() => window.__APOLLO_STATE__")  — JS 컨텍스트에서 직접
  2) HTML 안의 window.__APOLLO_STATE__ = {...}; 정규식 + 브레이스 카운팅
  3) page.content() 의 raw HTML 폴백
  4) 페이지 로드 중 가로챈 XHR JSON 응답들

발견 못 한 경우 _debug/detail_{id}_{label}/ 폴더에 모든 응답과 페이지 HTML
저장 — 직접 들여다보고 패턴 맞출 수 있게.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PWTimeout

HOME_URL = "https://pcmap.place.naver.com/restaurant/{pid}/home"
MENU_URL = "https://pcmap.place.naver.com/restaurant/{pid}/menu/list"

NAVIGATION_TIMEOUT = 25_000
NETWORKIDLE_TIMEOUT = 8_000

DEBUG_DIR = Path(__file__).resolve().parent / "_debug"
KOR_DAY_ORDER = ["월", "화", "수", "목", "금", "토", "일"]


@dataclass
class Menu:
    name: str
    price: str = ""


@dataclass
class BusinessHour:
    day_of_week: str
    open_time: str = ""
    close_time: str = ""
    is_closed: bool = False


@dataclass
class PlaceDetail:
    place_id: str
    name: str = ""
    address: str = ""
    menus: list[Menu] = field(default_factory=list)
    hours: list[BusinessHour] = field(default_factory=list)


def _debug_enabled(verbose: Optional[bool]) -> bool:
    if verbose is not None:
        return verbose
    return bool(os.environ.get("DEBUG"))


def _walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dicts(v)


def _normalize_day(day: str) -> Optional[str]:
    day = day.strip()
    if not day:
        return None
    if day[0] in KOR_DAY_ORDER:
        return day[0]
    en = {
        "MONDAY": "월", "MON": "월",
        "TUESDAY": "화", "TUE": "화",
        "WEDNESDAY": "수", "WED": "수",
        "THURSDAY": "목", "THU": "목",
        "FRIDAY": "금", "FRI": "금",
        "SATURDAY": "토", "SAT": "토",
        "SUNDAY": "일", "SUN": "일",
    }
    return en.get(day.upper())


# ---------- APOLLO_STATE 추출 ----------

def _get_apollo_via_js(page: Page) -> Optional[dict]:
    """JS 컨텍스트에서 window.__APOLLO_STATE__ 를 직접 읽는다.

    페이지의 inline script 가 React 마운트 후 제거되더라도 window 변수는
    유효하므로 가장 안정적인 경로.
    """
    try:
        return page.evaluate(
            "() => (typeof window.__APOLLO_STATE__ !== 'undefined') "
            "? JSON.parse(JSON.stringify(window.__APOLLO_STATE__)) : null"
        )
    except Exception:
        return None


def _get_apollo_via_html(html: str) -> Optional[dict]:
    """HTML 에 박힌 'window.__APOLLO_STATE__ = {...};' 추출.

    정규식의 non-greedy 매칭은 중첩 JSON 에서 망가지므로 brace counting 사용.
    """
    marker = "window.__APOLLO_STATE__"
    idx = html.find(marker)
    if idx < 0:
        return None
    eq = html.find("=", idx + len(marker))
    if eq < 0:
        return None
    start = html.find("{", eq)
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    end = -1
    for i in range(start, len(html)):
        ch = html[i]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end < 0:
        return None
    try:
        return json.loads(html[start:end])
    except json.JSONDecodeError:
        return None


# ---------- 메뉴 / 영업시간 파싱 ----------

def _parse_menus(state: dict) -> list[Menu]:
    """Apollo state 안의 'Menu' 타입 객체 추출."""
    out: list[Menu] = []
    seen: set[tuple[str, str]] = set()

    for d in _walk_dicts(state):
        typename = str(d.get("__typename") or "")
        if typename and "Menu" not in typename:
            continue
        name = d.get("name")
        price = d.get("price")
        if not isinstance(name, str) or not name:
            continue
        if price is None:
            continue
        price_s = str(price).strip()
        if not price_s or price_s == "0":
            continue
        # __typename 이 없는데 name+price 가 있다면 메뉴가 아닐 수도. 보수적으로 typename 필요.
        if not typename:
            continue
        key = (name.strip(), price_s)
        if key in seen:
            continue
        seen.add(key)
        out.append(Menu(name=name.strip(), price=price_s))
    return out


def _parse_hours(state: dict) -> list[BusinessHour]:
    """Apollo state 안의 영업시간 정보 추출.

    네이버는 'openingHours' 필드 또는 'BusinessHour' 타입 객체로 노출한다.
    형태가 다양해서 day/dayOfWeek 등의 키를 가진 dict 를 모두 후보로 검사.
    """
    out: list[BusinessHour] = []
    found: set[str] = set()

    for d in _walk_dicts(state):
        day = (
            d.get("day")
            or d.get("dayOfWeek")
            or d.get("dayOfWeekKr")
            or d.get("dayName")
        )
        if not isinstance(day, str) or not day:
            continue
        kor = _normalize_day(day)
        if kor is None or kor in found:
            continue

        is_closed = bool(
            d.get("isDayOff") or d.get("closed") or d.get("dayOff") or d.get("isClosed")
        )

        open_t = d.get("openTime") or d.get("open") or d.get("start") or ""
        close_t = d.get("closeTime") or d.get("close") or d.get("end") or ""

        if (not open_t or not close_t) and isinstance(d.get("businessHours"), list):
            inner = d["businessHours"]
            if inner and isinstance(inner[0], dict):
                open_t = open_t or inner[0].get("start") or inner[0].get("openTime") or ""
                close_t = close_t or inner[0].get("end") or inner[0].get("closeTime") or ""

        if not (is_closed or open_t or close_t):
            continue

        found.add(kor)
        out.append(BusinessHour(
            day_of_week=kor,
            open_time=str(open_t),
            close_time=str(close_t),
            is_closed=is_closed,
        ))

    out.sort(key=lambda h: KOR_DAY_ORDER.index(h.day_of_week) if h.day_of_week in KOR_DAY_ORDER else 99)
    return out


# ---------- DOM 기반 영업시간 추출 (Apollo state 폴백) ----------

# 사용자 제보로 확인된 영업시간 컨테이너 클래스. obfuscated 이라 빌드마다 변할 수 있음.
HOURS_CONTAINER_SELECTORS = [
    "div.H3ua4",
    "[class*='H3ua4']",
]

# "월 10:00 - 22:00" / "월요일 10:00 ~ 22:00" 등
_RE_DAY_OPEN = __import__("re").compile(
    r"(?P<day>[월화수목금토일])(?:요일)?[\s:.]*(?P<open>\d{1,2}:\d{2})\s*[-~∼]\s*(?P<close>\d{1,2}:\d{2})"
)
# "수요일 휴무" / "월 정기휴무"
_RE_DAY_CLOSED = __import__("re").compile(
    r"(?P<day>[월화수목금토일])(?:요일)?[\s:.]*(?:정기)?(?:휴무|휴일)"
)


def _is_hours_expanded(page: Page) -> bool:
    """DOM 의 텍스트에 '월요일'~'일요일' 중 3개 이상이 들어있으면 펼쳐진 상태."""
    try:
        return page.evaluate(
            "() => { const t = document.body.innerText || ''; "
            "const days = ['월요일','화요일','수요일','목요일','금요일','토요일','일요일']; "
            "return days.filter(d => t.includes(d)).length >= 3; }"
        )
    except Exception:
        return False


def _expand_hours_block(page: Page, debug: bool) -> None:
    """영업시간 블록을 펼치도록 여러 전략을 순차 시도.

    네이버는 chevron 아이콘 (텍스트 없는 토글) 을 쓰는 경우가 많아서
    텍스트 기반 셀렉터만으론 부족하다.
    """
    if _is_hours_expanded(page):
        if debug:
            print(f"  [DEBUG] hours 이미 펼쳐짐")
        return

    strategies: list[tuple[str, str]] = [
        ("text=펼치기 버튼", "css=button:has-text('펼치기'), css=a:has-text('펼치기')"),
        ("aria-expanded=false", "css=[aria-expanded='false']"),
        # '영업 중' / '영업 종료' / '영업시간' 텍스트가 있는 클릭 가능 요소
        ("영업 텍스트 근처 role=button", "css=a[role='button']:has-text('영업'), button:has-text('영업')"),
        # H3ua4 같은 영업시간 컨테이너 내의 첫 클릭 가능 요소
        ("영업시간 컨테이너 내부", "css=div.H3ua4 a[role='button'], div.H3ua4 button, [class*='H3ua4'] a[role='button']"),
    ]

    for label, sel in strategies:
        try:
            loc = page.locator(sel).first
            if not loc.count():
                continue
            try:
                if not loc.is_visible():
                    continue
            except Exception:
                continue
            loc.click(timeout=1500)
            page.wait_for_timeout(500)
            if debug:
                print(f"  [DEBUG] hours expand 시도: {label}")
            if _is_hours_expanded(page):
                if debug:
                    print(f"  [DEBUG] hours 펼쳐짐 ✓")
                return
        except Exception as e:
            if debug:
                print(f"  [DEBUG] hours expand 실패 ({label}): {e}")
            continue

    # 마지막 전략: '영업시간' 라벨의 같은 영역에서 클릭 가능한 모든 후보를 차례로 시도
    try:
        anchor = page.get_by_text("영업시간", exact=False).first
        if anchor.count():
            container = anchor.locator("xpath=ancestor::div[1]")
            clickables = container.locator("css=a[role='button'], button, [aria-expanded]")
            n = min(clickables.count(), 5)
            for i in range(n):
                try:
                    clickables.nth(i).click(timeout=1000)
                    page.wait_for_timeout(400)
                    if _is_hours_expanded(page):
                        if debug:
                            print(f"  [DEBUG] hours 펼쳐짐 (anchor 형제 #{i})")
                        return
                except Exception:
                    continue
    except Exception:
        pass

    if debug and not _is_hours_expanded(page):
        print(f"  [DEBUG] hours: 모든 펼치기 시도 실패")


def _read_hours_text(page: Page, debug: bool) -> str:
    """영업시간 컨테이너에서 텍스트를 읽어온다.

    1순위: HOURS_CONTAINER_SELECTORS
    2순위: '영업시간' 텍스트 앵커의 조상 컨테이너 (level 1, 2, 3 순회)
    펼침 검증: 결과 텍스트에 요일이 3개 이상 등장해야 진짜 펼쳐진 영업시간.
    """
    def _has_multiple_days(t: str) -> bool:
        return sum(1 for d in KOR_DAY_ORDER if d in t) >= 3

    candidates: list[tuple[str, str]] = []  # (label, text)

    for sel in HOURS_CONTAINER_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count():
                text = loc.inner_text(timeout=1500)
                if text:
                    candidates.append((f"selector={sel}", text))
        except Exception:
            continue

    # '영업시간' 앵커 부모를 단계별로 확장하며 시도
    try:
        anchor = page.get_by_text("영업시간", exact=False).first
        if anchor.count():
            for depth in (1, 2, 3, 4):
                try:
                    container = anchor.locator(f"xpath=ancestor::div[{depth}]").first
                    text = container.inner_text(timeout=1500)
                    if text:
                        candidates.append((f"anchor-depth={depth}", text))
                except Exception:
                    continue
    except Exception:
        pass

    # 다요일이 들어있는 후보를 우선
    for label, text in candidates:
        if _has_multiple_days(text):
            if debug:
                print(f"  [DEBUG] hours DOM: {label}, text={len(text)}자, 요일 다수 ✓")
            return text

    # 단일 요일 (= 펼치기 실패)도 폴백으로 반환
    if candidates:
        label, text = candidates[0]
        if debug:
            print(f"  [DEBUG] hours DOM: {label}, text={len(text)}자, 요일 부족 (펼치기 실패 의심)")
        return text

    return ""


def _parse_hours_text(text: str) -> list[BusinessHour]:
    """DOM 텍스트에서 요일별 영업시간 추출. 한 요일은 한 번만 잡는다."""
    import re
    # 줄바꿈/공백 정리: '월요일\n10:00 - 22:00' 같은 형태도 한 줄로 흘려서 매칭
    flat = re.sub(r"[ \t]+", " ", text)
    flat = re.sub(r"\n+", " ", flat).strip()

    out: list[BusinessHour] = []
    seen: set[str] = set()

    for m in _RE_DAY_OPEN.finditer(flat):
        d = m.group("day")
        if d in seen:
            continue
        seen.add(d)
        out.append(BusinessHour(
            day_of_week=d,
            open_time=m.group("open"),
            close_time=m.group("close"),
        ))

    for m in _RE_DAY_CLOSED.finditer(flat):
        d = m.group("day")
        if d in seen:
            continue
        seen.add(d)
        out.append(BusinessHour(day_of_week=d, is_closed=True))

    out.sort(key=lambda h: KOR_DAY_ORDER.index(h.day_of_week))
    return out


def _parse_hours_from_dom(page: Page, place_id: str, debug: bool) -> list[BusinessHour]:
    """페이지 DOM 에서 영업시간 추출 — Apollo state 가 비어있을 때 폴백.

    파싱 실패 시 추출한 raw 텍스트를 _debug 폴더에 저장 (정규식 보강용).
    """
    _expand_hours_block(page, debug)
    text = _read_hours_text(page, debug)
    if not text:
        return []
    parsed = _parse_hours_text(text)
    if debug:
        print(f"  [DEBUG] hours DOM: 파싱 결과 {len(parsed)}건")
    if not parsed:
        DEBUG_DIR.mkdir(exist_ok=True)
        path = DEBUG_DIR / f"hours_text_{place_id}.txt"
        path.write_text(text, encoding="utf-8")
        if debug:
            print(f"  [DEBUG] DOM 텍스트 dump → {path}")
    return parsed


# ---------- 페이지 네비게이션 + XHR 캡처 ----------

def _navigate_and_capture(
    page: Page,
    url: str,
    label: str,
    debug: bool,
) -> tuple[Optional[dict], list[tuple[str, dict]], str]:
    """url 로 이동, XHR 응답 캡처, APOLLO_STATE 와 raw HTML 도 함께 반환.

    반환: (apollo_state or None, xhr_responses, raw_html)
    """
    captured: list[tuple[str, dict]] = []

    def _on_response(resp):
        ctype = resp.headers.get("content-type", "")
        if "json" not in ctype.lower():
            return
        try:
            data = resp.json()
        except Exception:
            return
        if isinstance(data, (dict, list)):
            captured.append((resp.url, data))

    page.on("response", _on_response)
    try:
        if debug:
            print(f"  [DEBUG] navigate ({label}) {url}")
        try:
            page.goto(url, timeout=NAVIGATION_TIMEOUT, wait_until="domcontentloaded")
        except PWTimeout:
            if debug:
                print(f"  [DEBUG] navigation 타임아웃 (계속)")

        # 1) DOMContentLoaded 직후 raw HTML 확보 — 이 시점이 inline script 가 가장 잘 살아있음
        early_html = page.content()
        early_state = _get_apollo_via_html(early_html)

        # 2) networkidle 까지 대기 (XHR 들이 도착)
        try:
            page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_TIMEOUT)
        except PWTimeout:
            if debug:
                print(f"  [DEBUG] networkidle 타임아웃 (계속)")
        page.wait_for_timeout(300)

        # 3) JS 컨텍스트에서 한 번 더 시도 (가장 신뢰)
        js_state = _get_apollo_via_js(page)

        late_html = page.content()
    finally:
        page.remove_listener("response", _on_response)

    state = js_state or early_state or _get_apollo_via_html(late_html)

    if debug:
        sources = []
        if js_state: sources.append("page.evaluate")
        if not js_state and early_state: sources.append("HTML(early)")
        if not js_state and not early_state and state: sources.append("HTML(late)")
        src = ",".join(sources) if sources else "없음"
        print(f"  [DEBUG] {label}: APOLLO_STATE={src}, XHR JSON {len(captured)}건")

    return state, captured, late_html


def _save_debug_dumps(
    place_id: str,
    label: str,
    captured: list[tuple[str, dict]],
    full_html: str,
    state: Optional[dict],
) -> Path:
    folder = DEBUG_DIR / f"detail_{place_id}_{label}"
    folder.mkdir(parents=True, exist_ok=True)
    index_lines: list[str] = []
    for i, (url, data) in enumerate(captured):
        slug = url.split("?", 1)[0].split("/")[-1] or f"resp{i}"
        slug = "".join(c if c.isalnum() else "_" for c in slug)[:30]
        fname = f"{i:02d}__{slug}.json"
        try:
            (folder / fname).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            (folder / fname).write_text(str(data)[:50_000], encoding="utf-8")
        index_lines.append(f"{fname}\t{url}")
    (folder / "_index.tsv").write_text("\n".join(index_lines), encoding="utf-8")
    if full_html:
        (folder / "_page.html").write_text(full_html[:2_000_000], encoding="utf-8", errors="replace")
    if state is not None:
        try:
            (folder / "_apollo_state.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2)[:1_000_000],
                encoding="utf-8",
            )
        except Exception:
            pass
    return folder


def fetch_detail(
    place_id: str,
    page: Page,
    verbose: Optional[bool] = None,
) -> PlaceDetail:
    """home + menu 페이지를 받아 메뉴/영업시간 추출."""
    debug = _debug_enabled(verbose)
    detail = PlaceDetail(place_id=str(place_id))

    # ---- home 페이지 (영업시간) ----
    state, xhrs, html = _navigate_and_capture(
        page, HOME_URL.format(pid=place_id), "home", debug
    )
    if state:
        detail.hours = _parse_hours(state)
    if not detail.hours:
        # XHR 응답 폴백
        for url, data in xhrs:
            hrs = _parse_hours(data)
            if hrs:
                detail.hours = hrs
                if debug:
                    print(f"  [DEBUG] 영업시간 (XHR) in {url}")
                break

    # DOM 폴백 — state 의 openingHours 가 null 이어도 화면엔 렌더되는 경우
    if not detail.hours:
        detail.hours = _parse_hours_from_dom(page, place_id, debug)

    if not detail.hours and debug:
        folder = _save_debug_dumps(place_id, "home", xhrs, html, state)
        print(f"  [DEBUG] 영업시간 없음 — 덤프: {folder}")

    # ---- menu/list 페이지 (메뉴) ----
    state, xhrs, html = _navigate_and_capture(
        page, MENU_URL.format(pid=place_id), "menu", debug
    )
    if state:
        detail.menus = _parse_menus(state)
    if not detail.menus:
        for url, data in xhrs:
            ms = _parse_menus(data)
            if ms:
                detail.menus = ms
                if debug:
                    print(f"  [DEBUG] 메뉴 (XHR) in {url}")
                break

    if not detail.menus and debug:
        folder = _save_debug_dumps(place_id, "menu", xhrs, html, state)
        print(f"  [DEBUG] 메뉴 없음 — 덤프: {folder}")

    return detail


if __name__ == "__main__":
    import sys
    from browser import browser_session

    pid = sys.argv[1] if len(sys.argv) > 1 else "11583195"
    with browser_session() as page:
        d = fetch_detail(pid, page=page, verbose=True)
    print(f"\nplace_id: {d.place_id}")
    print(f"메뉴 {len(d.menus)}건:")
    for m in d.menus[:15]:
        print(f"  - {m.name}: {m.price}")
    print(f"영업시간 {len(d.hours)}건:")
    for h in d.hours:
        if h.is_closed:
            print(f"  - {h.day_of_week}: 휴무")
        else:
            print(f"  - {h.day_of_week}: {h.open_time} ~ {h.close_time}")
    input("\n계속하려면 Enter 키를 누르세요...")
