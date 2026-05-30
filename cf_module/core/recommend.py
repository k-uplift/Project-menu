from cf_module.data.synthetic import get_synthetic_dataset
from cf_module.models import (
    FoodKind,
    MenuAction,
    SearchSession,
    RecommendationResult,
    RecommendationResponse,
)


# 추후 DB/서비스 연동 시 어댑터 주입으로 교체될 부분.
_KINDS: list[FoodKind]
_SESSIONS: list[SearchSession]
_KINDS, _SESSIONS = get_synthetic_dataset()


def _get_user_final_selected_kinds(user_id: int) -> set[int]:
    """
    본인이 final_select한 kind_id 집합 반환.
    탭 1, 탭 2 모두에서 추천 후보 제외용으로 사용.

    클릭만 한 메뉴는 제외하지 않음 (다시 추천 가능).
    final_select한 메뉴만 제외 (이미 결정한 메뉴 또 추천은 무의미).
    """
    final_selected_kind_ids: set[int] = set()

    for session in _SESSIONS:
        if session.user_id != user_id:
            continue
        for action in session.actions:
            if action.action_type == "final_select":
                final_selected_kind_ids.add(action.kind_id)

    return final_selected_kind_ids


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

    알고리즘:
    1. 본인이 final_select한 kind_id 집합 조회 (제외 대상)
    2. 각 kind에 대해 score 계산:
       score = |input_tags ∩ kind.tags|
    3. score > 0이고 제외 대상이 아닌 kind만 수집
    4. score 내림차순 정렬
    5. 상위 top_k 반환

    matched_tags: 입력과 겹친 태그 리스트
    reason: 매칭된 태그를 #으로 표시
    """
    if not input_tags:
        return []

    unique_input_tags = list(dict.fromkeys(input_tags))
    excluded_kind_ids = _get_user_final_selected_kinds(user_id)
    results = []

    for kind in _KINDS:
        if kind.kind_id in excluded_kind_ids:
            continue

        kind_tags = set(kind.tags)
        matched_tags = [tag for tag in unique_input_tags if tag in kind_tags]
        score = len(matched_tags)

        if score == 0:
            continue

        formatted_tags = " ".join(f"#{tag}" for tag in matched_tags)
        reason = f"{formatted_tags} 태그가 잘 맞아요"

        results.append(
            RecommendationResult(
                kind_id=kind.kind_id,
                kind_name=kind.name,
                score=float(score),
                matched_tags=matched_tags,
                reason=reason,
            )
        )

    results.sort(key=lambda result: (-result.score, result.kind_id))
    return results[:top_k]


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
