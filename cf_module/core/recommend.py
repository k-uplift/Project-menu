from cf_module.models import RecommendationResult, RecommendationResponse


def recommend(
    input_tags: list[str],
    user_id: int,
    top_k: int = 5
) -> RecommendationResponse:
    """
    메인 추천 함수. 두 탭 결과를 함께 반환.
    내부적으로 recommend_tab1과 recommend_tab2_cf를 호출하고 겹침 처리.
    """
    raise NotImplementedError


def recommend_tab1(
    input_tags: list[str],
    user_id: int,
    top_k: int = 5
) -> list[RecommendationResult]:
    """
    탭 1: 입력 태그와 메뉴 태그 매칭 (콘텐츠 기반).

    점수: |input_tags ∩ kind.tags|
    reason 예: "#얼큰한 #국물있는 태그가 잘 맞아요"
    """
    raise NotImplementedError


def recommend_tab2_cf(
    input_tags: list[str],
    user_id: int,
    top_k: int = 5,
    tab1_kind_ids: list[int] = None
) -> list[RecommendationResult]:
    """
    탭 2: 세션 기반 CF.

    1. 본인 세션 제외한 모든 세션과 Jaccard 유사도 계산
    2. 매칭된 세션의 actions로 메뉴 점수 집계
    3. 본인이 final_select한 메뉴 제외
    4. tab1_kind_ids 상위 3개와 겹치는 메뉴는 최대 1개까지만 허용

    reason 예: "비슷한 입력의 사용자들이 자주 선택한 메뉴예요"
    """
    raise NotImplementedError
