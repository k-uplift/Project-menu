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
사용자 자연어 입력을 보고 네 종류의 신호를 분리해서 반환하세요.

시드 어휘(긍정·부정 모두 이 안에서만 고름): {seed}

규칙:
- tags: 사용자가 '원하는' 시드 0~4개.
  - 사용자 표현은 의미가 가장 가까운 시드로 매핑합니다.
    (예: "칼칼한"→"얼큰한", "비 오는 날"→"따뜻한"+"국물있는", "느끼한"→"고소한")
  - 음식·식사 의도가 *조금이라도* 있으면 가장 가까운 시드 1개라도 추측하세요.
    (예: "부산인데 음식 추천"→["든든한"] 일반 식사 추천 / "비싸도 맛있는"→["진한"] 풍부함)
  - 단 *완전히 음식 무관*(노이즈·인사·날씨)인 입력은 그대로 빈 배열.
    (예: "ㅋㅋㅋ", "도와줘", "오늘 날씨 어때" → tags=[])
- exclude_tags: 사용자가 '거부한' 시드 0~4개.
  - 명시적 부정 표현이 붙은 단어는 tags가 아니라 exclude_tags에 넣습니다.
  - 부정 표지: "X 말고", "X 빼고", "X 말고는", "X 없는", "안 X", "X 제외", "X 싫어".
  - 예: "매운 거 말고 담백한 거" → tags=["담백한"], exclude_tags=["얼큰한"]
        "단 거 말고 담백한 야식" → tags=["담백한","야식"], exclude_tags=["달달한"]
        "느끼한 거 빼고"        → tags=[], exclude_tags=["고소한"]
  - 부정된 단어를 절대 tags에 넣지 마세요 — 사용자 의도가 정반대가 됩니다.
  - 중요 (exclude만 해당): 위 부정 표지가 입력에 직접 등장한 경우에만 exclude_tags를
    채웁니다. 정황·암묵 추론으로 *거부*를 만들지 마세요. 예: "조용한 자리에서"는
    분위기 묘사일 뿐 어떤 시드도 거부하지 않습니다 → exclude_tags=[].
  - 단 tags(긍정)는 정황 추론을 적극 사용하세요. line 26의 "비 오는 날"→
    ["따뜻한","국물있는"] 처럼 시간·상황·날씨 컨텍스트도 가장 가까운 시드로 매핑.
- food_keywords: '음식 종류/식재료' 단어 0~6개. (open vocab — 시드 밖 자유 입력)
  - 시드는 음식의 *속성*만 다룹니다. 카테고리·식재료(고기/면/회/치킨/밥/국수/삼겹살 등)는
    여기로 넣으세요. 시드에 없는 단어를 억지로 시드로 매핑하지 마세요.
  - 메뉴명 substring 매칭에 쓰이므로, 가능하면 직접적인 동의어·하위어를 1~3개 함께
    넣어 검색 폭을 넓힙니다. (예: "고기"→["고기","삼겹살","갈비"],
    "면"→["면","국수","파스타"], "회"→["회","사시미","초밥"],
    "치킨"→["치킨","후라이드","강정"])
  - 입력에 음식 단어가 직접 없어도, *맥락·상황이 전형 음식을 강하게 시사*하면
    2~4개 추측해서 넣으세요. 단 자의적 추측은 자제 (확신 있는 것만).
    예: "회식" → ["고기","삼겹살","찜닭","찌개"]   (회식 전형)
    예: "출근 전 빠르게" → ["김밥","토스트","샌드위치"]  (간단 아침)
    예: "운동 후" → ["닭가슴살","샐러드","연어"]   (단백질·가벼움)
    예: "비 오는 날" → ["김치찌개","파전","칼국수"]
  - 단, 너무 멀리 가지 마세요(브랜드명·구체 가게명 X). 같은 음식의 흔한 다른 이름 정도.
  - 정말 어떤 음식도 떠올릴 단서가 없으면 빈 배열.
- exclude_food_keywords: '거부된 음식 종류' 0~4개.
  - 부정 표지가 붙은 음식 종류만. 예: "고기 말고 면" → food_keywords=["면","국수"],
    exclude_food_keywords=["고기","삼겹살","갈비"].
- 부정 채널 우선순위 (중요):
  - 부정된 단어가 시드로 매핑 가능하면 무조건 exclude_tags를 씁니다 (exclude_food_keywords X).
    "튀긴 거 말고" → "튀긴 거"는 바삭한 매핑 → exclude_tags=["바삭한"].
    "기름진 거 말고" → "기름진 거"는 고소한 매핑 → exclude_tags=["고소한"].
    "단 거 말고" → "단 거"는 달달한 매핑 → exclude_tags=["달달한"].
  - 시드 매핑 불가한 카테고리·식재료 단어(고기/면/회/치킨…)만 exclude_food_keywords로.
  - 시드 매핑 가능 단어를 exclude_food_keywords에 넣으면 추천이 망가집니다.
- 비음식·노이즈는 네 필드 모두 빈 배열.

출력은 JSON 한 줄만:
{{"tags": [...], "exclude_tags": [...], "food_keywords": [...], "exclude_food_keywords": [...]}}\
""".format(seed=list(SEED_TAGS))


# 구조화 출력 스키마 — Claude가 항상 이 JSON 형태로만 응답하게 강제.
# (output_config.format / Sonnet 4.6 지원).
#  - tags/exclude_tags: items enum으로 시드 14개 밖을 차단 → 쿼리·메뉴 양쪽이 같은
#    어휘를 써서 교집합 매칭이 항상 잘 정의된다.
#  - food_keywords/exclude_food_keywords: 카테고리·식재료(고기·면·회·치킨…)는 시드 차원
#    이 아니라 메뉴명 substring 차원이라 enum 없이 open vocab. 시드의 '속성' 의미론을
#    오염시키지 않으면서 카테고리축 부재 문제를 보완한다.
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
        "food_keywords": {
            "type": "array",
            "items": {"type": "string"},
        },
        "exclude_food_keywords": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["tags", "exclude_tags", "food_keywords", "exclude_food_keywords"],
    "additionalProperties": False,
}


@dataclass
class ExtractResult:
    original_text: str
    tags: list[str]
    source: str  # "claude" | "mock" | "fallback"
    exclude_tags: list[str] = None  # type: ignore[assignment]
    food_keywords: list[str] = None  # type: ignore[assignment]
    exclude_food_keywords: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # dataclass 기본값을 list로 두면 공유되므로 None → [] 변환을 사후처리한다.
        if self.exclude_tags is None:
            self.exclude_tags = []
        if self.food_keywords is None:
            self.food_keywords = []
        if self.exclude_food_keywords is None:
            self.exclude_food_keywords = []


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
        tags, excludes, fkw, excl_fkw = _parse_claude_json(raw)
        # exclude_tags ∩ tags가 있으면 의도 모순 — exclude를 우선해 tags에서 제거.
        excluded_set = set(excludes)
        tags = [t for t in tags if t not in excluded_set]
        # food_keywords도 대칭으로: exclude_food_keywords와 겹치면 거부 우선.
        excl_fkw_lower = {k.lower() for k in excl_fkw}
        fkw = [k for k in fkw if k.lower() not in excl_fkw_lower]
        return ExtractResult(
            original_text=text,
            tags=tags,
            source="claude",
            exclude_tags=excludes,
            food_keywords=fkw,
            exclude_food_keywords=excl_fkw,
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


def _parse_claude_json(
    raw: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Claude 응답 JSON 파싱. (tags, exclude_tags, food_keywords, exclude_food_keywords).

    tags/exclude_tags는 시드 정규화(SURFACE_TO_CANONICAL) 적용.
    food_keywords/exclude_food_keywords는 open vocab이라 정규화 없이 strip+lowercase만.
    """
    data = json.loads(raw)

    def _clean_seed(items) -> list[str]:
        return [normalize(t) for t in items if isinstance(t, str) and t.strip()][:4]

    def _clean_kw(items, cap: int) -> list[str]:
        # 중복은 보존 순서로 제거. 한국어는 1글자 음식어("회/면/밥/쌀/콩")가 흔해서
        # 길이 필터를 두지 않는다 — 빈 문자열만 거른다. 단일 알파벳 같은 영문 노이즈는
        # 메뉴명 매칭에서 자연스럽게 영향 적음.
        seen: set[str] = set()
        out: list[str] = []
        for k in items:
            if not isinstance(k, str):
                continue
            s = k.strip()
            if not s:
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
            if len(out) >= cap:
                break
        return out

    tags = _clean_seed(data.get("tags", []))
    excludes = _clean_seed(data.get("exclude_tags", []))
    fkw = _clean_kw(data.get("food_keywords", []), cap=6)
    excl_fkw = _clean_kw(data.get("exclude_food_keywords", []), cap=4)
    return tags, excludes, fkw, excl_fkw


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
        fkw = f"  food={r.food_keywords}" if r.food_keywords else ""
        excl_fkw = (
            f"  exclude_food={r.exclude_food_keywords}"
            if r.exclude_food_keywords
            else ""
        )
        print(f"[{r.source:8s}] {s!r:40s} → {r.tags}{excl}{fkw}{excl_fkw}")
