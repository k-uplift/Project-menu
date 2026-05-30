from collections import defaultdict

from cf_module.core.similarity import jaccard_similarity
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


def _get_kind_max_weights_in_session(session: SearchSession) -> dict[int, int]:
    """
    한 세션 안에서 각 kind의 최대 weight 반환.
    같은 kind에 click(1)과 final_select(2)가 둘 다 있으면 2만 반환.

    Returns:
        {kind_id: max_weight}
    """
    kind_weights: dict[int, int] = {}

    for action in session.actions:
        current_weight = kind_weights.get(action.kind_id, 0)
        kind_weights[action.kind_id] = max(current_weight, action.weight)

    return kind_weights


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

    알고리즘:
    1. 본인 세션은 비교에서 제외
    2. 본인이 final_select한 kind_id 집합 조회 (제외 대상)
    3. 모든 타인 세션에 대해:
       a. 세션 input_tags와 현재 input_tags의 Jaccard 유사도 계산
       b. 유사도 == 0이면 스킵
       c. 세션 actions를 kind별 최대 weight로 집계
          같은 세션 안에 같은 kind의 click과 final_select가 있으면 2만 카운트
       d. kind_score[kind_id] += similarity * max_weight_in_session
    4. 본인이 final_select한 메뉴 제외
    5. 점수 내림차순 정렬 (동점은 kind_id 오름차순)
    6. tab1_kind_ids가 있으면 탭 1 상위 3개와 겹치는 메뉴는 최대 1개만 허용
    7. 상위 top_k 반환

    matched_tags: 추천된 kind의 태그 중 입력 태그와 겹치는 것
                  (참고용, CF 점수 자체엔 영향 없음)
    reason: "비슷한 입력의 사용자들이 자주 선택한 메뉴예요"
    """
    if not input_tags or top_k <= 0:
        return []

    unique_input_tags = list(dict.fromkeys(input_tags))
    current_tag_set = set(unique_input_tags)
    excluded_kind_ids = _get_user_final_selected_kinds(user_id)
    kind_scores: dict[int, float] = defaultdict(float)

    for session in _SESSIONS:
        if session.user_id == user_id:
            continue

        similarity = jaccard_similarity(current_tag_set, set(session.input_tags))
        if similarity == 0:
            continue

        kind_max_weights = _get_kind_max_weights_in_session(session)
        for kind_id, max_weight in kind_max_weights.items():
            if kind_id in excluded_kind_ids:
                continue
            kind_scores[kind_id] += similarity * max_weight

    kind_by_id = {kind.kind_id: kind for kind in _KINDS}
    sorted_scores = sorted(kind_scores.items(), key=lambda item: (-item[1], item[0]))
    top_tab1_kind_ids = set(tab1_kind_ids[:3]) if tab1_kind_ids is not None else set()
    tab1_overlap_count = 0
    results = []

    for kind_id, score in sorted_scores:
        if kind_id in top_tab1_kind_ids:
            tab1_overlap_count += 1
            if tab1_overlap_count > 1:
                continue

        kind = kind_by_id[kind_id]
        kind_tags = set(kind.tags)
        matched_tags = [tag for tag in unique_input_tags if tag in kind_tags]

        results.append(
            RecommendationResult(
                kind_id=kind.kind_id,
                kind_name=kind.name,
                score=score,
                matched_tags=matched_tags,
                reason="비슷한 입력의 사용자들이 자주 선택한 메뉴예요",
            )
        )

        if len(results) >= top_k:
            break

    return results
