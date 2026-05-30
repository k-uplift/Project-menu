from dataclasses import dataclass, field


FIXED_TAGS = [
    "따뜻한", "시원한", "얼큰한", "국물있는", "담백한",
    "진한", "가벼운", "든든한", "해장", "야식",
    "바삭한", "쫄깃한", "고소한", "달달한"
]


@dataclass
class RecommendationResult:
    """추천 결과 단일 항목."""

    kind_id: int
    kind_name: str
    score: float
    matched_tags: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class RecommendationResponse:
    """추천 응답. 두 탭 결과를 함께 담음."""

    tab1_results: list[RecommendationResult]
    tab2_results: list[RecommendationResult]
    input_tags: list[str]
    user_id: int
