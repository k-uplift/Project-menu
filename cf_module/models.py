from dataclasses import dataclass, field
from enum import IntEnum


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
    tab2_empty_reason: str | None = None


class ActionWeight(IntEnum):
    """행동별 가중치. 한 곳에 박아두고 알고리즘에서 참조."""

    CLICK = 1
    FINAL_SELECT = 2


@dataclass
class FoodKind:
    """음식 종류 (kind). CF의 추천 단위.

    실제 시스템에서는 LLM 팀의 292개 kind 중 하나에 해당.
    가게별 raw 메뉴가 아닌 추상 음식 종류.
    """

    kind_id: int
    name: str
    tags: list[str]


@dataclass
class MenuAction:
    """한 세션 안의 행동.

    click=1점, final_select=2점. 좋아요는 이번 데모에서 제외.
    """

    kind_id: int
    action_type: str

    @property
    def weight(self) -> int:
        """action_type을 기반으로 가중치 반환."""
        if self.action_type == "click":
            return ActionWeight.CLICK
        if self.action_type == "final_select":
            return ActionWeight.FINAL_SELECT
        raise ValueError(f"Unknown action type: {self.action_type}")


@dataclass
class SearchSession:
    """검색 세션. CF의 핵심 비교 단위.

    '어떤 입력 태그로 검색했을 때 무엇을 골랐는가'를 묶어서 저장.
    사용자 프로필이 아닌 세션 단위로 저장.
    같은 사용자도 검색마다 의도가 다르기 때문.
    """

    session_id: int
    user_id: int
    input_tags: list[str]
    actions: list[MenuAction] = field(default_factory=list)
    timestamp: str = ""
