"""자연어 → 추천 태그 추출.

5/17 회의 확정: 태그 추출이 메인. 시드 14개에서만 1~4개 추출(쿼리·메뉴 동일 어휘).
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
사용자 자연어 입력을 보고 두 종류의 시드를 분리해서 반환하세요.

시드 어휘(긍정·부정 모두 이 안에서만 고름): {seed}

규칙:
- tags: 사용자가 '원하는' 시드 0~4개.
  - 사용자 표현은 의미가 가장 가까운 시드로 매핑합니다.
    (예: "칼칼한"→"얼큰한", "비 오는 날"→"따뜻한"+"국물있는", "느끼한"→"고소한")
- exclude_tags: 사용자가 '거부한' 시드 0~4개.
  - 명시적 부정 표현이 붙은 단어는 tags가 아니라 exclude_tags에 넣습니다.
  - 부정 표지: "X 말고", "X 빼고", "X 말고는", "X 없는", "안 X", "X 제외", "X 싫어".
  - 예: "매운 거 말고 담백한 거" → tags=["담백한"], exclude_tags=["얼큰한"]
        "단 거 말고 담백한 야식" → tags=["담백한","야식"], exclude_tags=["달달한"]
        "느끼한 거 빼고"        → tags=[], exclude_tags=["고소한"]
  - 부정된 단어를 절대 tags에 넣지 마세요 — 사용자 의도가 정반대가 됩니다.
  - 중요: 위 부정 표지가 입력에 직접 등장한 경우에만 exclude_tags를 채웁니다.
    정황·암묵 추론으로 거부를 만들지 마세요. 예: "출근 전 빠르게"는 명시적 부정이
    아니므로 exclude_tags=[]. 시간·상황 컨텍스트만으로 시드를 거부하지 않습니다.
- 비음식·노이즈는 둘 다 빈 배열. 의미가 전혀 없으면 빈 배열을 반환합니다.

출력은 JSON 한 줄만:
{{"tags": ["...", "..."], "exclude_tags": ["..."]}}\
""".format(seed=list(SEED_TAGS))


# 구조화 출력 스키마 — Claude가 항상 이 JSON 형태로만 응답하게 강제.
# (output_config.format / Sonnet 4.6 지원). items enum으로 시드 14개 밖 태그를 차단
# → 쿼리·메뉴 양쪽이 같은 어휘를 써서 매칭(교집합)이 항상 잘 정의된다.
# exclude_tags는 부정 표현을 별도 채널로 받아 enum 잠금과 부정 처리를 양립시킨다.
TAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {"type": "string", "enum": list(SEED_TAGS)},
        },
        "exclude_tags": {
            "type": "array",
            "items": {"type": "string", "enum": list(SEED_TAGS)},
        },
    },
    "required": ["tags", "exclude_tags"],
    "additionalProperties": False,
}


@dataclass
class ExtractResult:
    original_text: str
    tags: list[str]
    source: str  # "claude" | "mock" | "fallback"
    exclude_tags: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # dataclass 기본값을 list로 두면 공유되므로 None → [] 변환을 사후처리한다.
        if self.exclude_tags is None:
            self.exclude_tags = []


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
        tags, excludes = _parse_claude_json(raw)
        # exclude_tags ∩ tags가 있으면 의도 모순 — exclude를 우선해 tags에서 제거.
        excluded_set = set(excludes)
        tags = [t for t in tags if t not in excluded_set]
        return ExtractResult(
            original_text=text, tags=tags, source="claude", exclude_tags=excludes
        )
    except Exception as e:  # 네트워크/레이트리밋/스키마 등 → mock 폴백
        print(f"[extract] Claude 호출 실패({type(e).__name__}) → mock 폴백")
        return _extract_mock(text)


def _extract_mock(text: str) -> ExtractResult:
    """규칙 기반 mock — SURFACE_TO_CANONICAL 부분문자열 매칭. 시드 정규형만 출력.

    mock은 부정 처리를 하지 않는다(어휘에 우연히 빠진 단어가 무시되는 효과로
    부정처럼 보일 수는 있음). 부정이 필요하면 Claude를 쓸 것.
    """
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


def _parse_claude_json(raw: str) -> tuple[list[str], list[str]]:
    """Claude 응답 JSON 파싱 + 정규화. (tags, exclude_tags) 둘 다 정규화 적용."""
    data = json.loads(raw)
    tags_raw = data.get("tags", [])
    excludes_raw = data.get("exclude_tags", [])

    def _clean(items) -> list[str]:
        return [normalize(t) for t in items if isinstance(t, str) and t.strip()][:4]

    return _clean(tags_raw), _clean(excludes_raw)


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
        excl = f"  exclude={r.exclude_tags}" if r.exclude_tags else ""
        print(f"[{r.source:8s}] {s!r:40s} → {r.tags}{excl}")
