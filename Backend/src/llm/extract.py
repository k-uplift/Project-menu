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


# 구조화 출력 스키마 — Claude가 항상 이 JSON 형태로만 응답하게 강제.
# (output_config.format / Sonnet 4.6 지원). tags는 문자열 배열.
TAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tags"],
    "additionalProperties": False,
}


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
    """Claude(Sonnet 4.6) 호출로 태그 추출. 실패 시 mock으로 폴백.

    - 구조화 출력(output_config.format)으로 JSON 형태를 강제 → 파싱 안정.
    - 단순 추출 작업이라 thinking은 끔(기본). max_tokens는 짧게.
    - system 프롬프트는 고정이라 cache_control을 달아둠(프리픽스가 모델 최소
      캐시 길이 이상일 때만 실제 캐시됨 — 짧으면 무시되며 비용 영향 없음).
    """
    try:
        import anthropic
    except ImportError:
        print("[extract] anthropic 미설치 → mock 폴백 (pip install anthropic)")
        return _extract_mock(text)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": text}],
            output_config={"format": {"type": "json_schema", "schema": TAGS_SCHEMA}},
        )
        raw = next((b.text for b in resp.content if b.type == "text"), "")
        tags = _parse_claude_json(raw)
        return ExtractResult(original_text=text, tags=tags, source="claude")
    except Exception as e:  # 네트워크/레이트리밋/스키마 등 → mock 폴백
        print(f"[extract] Claude 호출 실패({type(e).__name__}) → mock 폴백")
        return _extract_mock(text)


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
