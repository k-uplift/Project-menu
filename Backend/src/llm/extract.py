"""자연어 → 추천 태그 추출.

5/17 회의 확정: 태그 추출이 메인. 시드 13개에서만 1~4개 추출(쿼리·메뉴 동일 어휘).
API 키 수령 전엔 mock(규칙 기반)으로 동작 — 키 받으면 _extract_claude가 enum으로 강제.
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
- 다음 시드 어휘에서만 고릅니다: {seed}
- 사용자 표현은 의미가 가장 가까운 시드로 매핑합니다 (예: "칼칼한"→"얼큰한",
  "비 오는 날"→"따뜻한"+"국물있는", "느끼한"→"고소한").
- 부정은 "X 말고" 형태로 표기 (예: "매운 거 말고").
- 비음식·노이즈는 무시합니다. 의미가 전혀 없으면 빈 배열을 반환합니다.

출력은 JSON 한 줄만:
{{"tags": ["...", "..."]}}\
""".format(seed=list(SEED_TAGS))


# 구조화 출력 스키마 — Claude가 항상 이 JSON 형태로만 응답하게 강제.
# (output_config.format / Sonnet 4.6 지원). items enum으로 시드 13개 밖 태그를 차단
# → 쿼리·메뉴 양쪽이 같은 어휘를 써서 매칭(교집합)이 항상 잘 정의된다.
TAGS_SCHEMA = {
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
    """규칙 기반 mock — SURFACE_TO_CANONICAL 부분문자열 매칭. 시드 정규형만 출력."""
    hits: list[str] = []
    lowered = text.lower()
    for surface, canonical in SURFACE_TO_CANONICAL:
        if surface in lowered and canonical not in hits:
            hits.append(canonical)
            if len(hits) >= 4:
                break
    if not hits:
        return ExtractResult(original_text=text, tags=[text.strip()[:12]], source="fallback")
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
