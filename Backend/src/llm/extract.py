"""자연어 → 추천 태그 추출.

5/17 회의 확정: 태그 추출이 메인. 1~4개 추출, open vocab + 시드 정규화.
API 키 수령 전엔 mock(규칙 기반)으로 동작 — 키 받으면 _extract_claude만 채우면 됨.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .tags import SEED_TAGS, SURFACE_TO_CANONICAL, normalize

CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
당신은 한국어 음식 추천 시스템의 신호 추출 모듈입니다.
사용자 자연어 입력에서 '추천에 쓸 핵심 표현' 1~4개를 한국어 형용사/명사구로 추출하세요.

규칙:
- 가능하면 다음 시드 어휘를 우선 사용: {seed}
- 시드에 없는 자연스러운 표현은 새로 만들어도 됩니다 (예: "비 오는 날", "집밥 같은").
- 부정은 "X 말고" 형태로 표기 (예: "매운 거 말고").
- 비음식·노이즈는 무시합니다. 의미가 전혀 없으면 빈 배열을 반환합니다.

출력은 JSON 한 줄만:
{{"tags": ["...", "..."]}}\
""".format(seed=list(SEED_TAGS))


@dataclass
class ExtractResult:
    original_text: str
    tags: list[str]
    source: str  # "claude" | "mock" | "fallback"


def extract_tags(text: str) -> ExtractResult:
    """공개 API. ANTHROPIC_API_KEY 있으면 Claude, 없으면 mock."""
    if not text or not text.strip():
        return ExtractResult(original_text=text, tags=[], source="fallback")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return _extract_claude(text, api_key)
    return _extract_mock(text)


def _extract_claude(text: str, api_key: str) -> ExtractResult:
    raise NotImplementedError(
        "anthropic 클라이언트 미연결. API 키 수령 후 구현 (requirements.txt에 anthropic 추가)."
    )


def _extract_mock(text: str) -> ExtractResult:
    """규칙 기반 mock — Frontend keywordService.js의 13개 매칭과 동일 동작 + 정규화."""
    hits: list[str] = []
    lowered = text.lower()
    for surface, canonical in SURFACE_TO_CANONICAL:
        if surface in lowered and canonical not in hits:
            hits.append(canonical)
            if len(hits) >= 4:
                break
    if not hits:
        return ExtractResult(
            original_text=text,
            tags=[text.strip()[:12]],
            source="fallback",
        )
    return ExtractResult(original_text=text, tags=hits, source="mock")


def _parse_claude_json(raw: str) -> list[str]:
    """Claude 응답 JSON 파싱 + 정규화. _extract_claude 구현 시 사용."""
    data = json.loads(raw)
    tags = data.get("tags", [])
    return [normalize(t) for t in tags if isinstance(t, str) and t.strip()][:4]


if __name__ == "__main__":
    import sys
    samples = sys.argv[1:] or [
        "비 오는 날 따뜻한 거",
        "아 졸려, 든든한 거 먹고 싶어",
        "매운 거 말고 담백한 국물",
        "집밥 같은 곳",
        "",
    ]
    for s in samples:
        r = extract_tags(s)
        print(f"[{r.source:8s}] {s!r:40s} → {r.tags}")
