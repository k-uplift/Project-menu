"""Playwright 브라우저 세션 관리.

요구사항:
  pip install playwright
  playwright install chromium

환경변수:
  HEADLESS=0  → 브라우저 창을 띄워서 동작 확인 (기본: 1, 헤드리스)
  SLOW_MO=300 → 각 액션 사이 N ms 대기 (디버깅용, 기본 0)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
except ImportError as e:
    raise SystemExit(
        "[X] playwright 가 설치되어 있지 않습니다.\n"
        "    pip install playwright\n"
        "    playwright install chromium"
    ) from e


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 900}
LOCALE = "ko-KR"
TIMEZONE = "Asia/Seoul"


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.lower() not in ("0", "false", "no", "")


@contextmanager
def browser_session() -> Iterator[Page]:
    """Playwright 브라우저를 띄워 page 를 yield. 종료 시 자동 정리."""
    headless = _env_bool("HEADLESS", default=True)
    slow_mo = int(os.environ.get("SLOW_MO", "0") or "0")

    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context: BrowserContext = browser.new_context(
            user_agent=USER_AGENT,
            viewport=VIEWPORT,
            locale=LOCALE,
            timezone_id=TIMEZONE,
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        # navigator.webdriver 숨기기 (간단한 봇 탐지 우회)
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page: Page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()
