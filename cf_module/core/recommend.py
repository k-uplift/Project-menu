from collections import defaultdict

from cf_module.core.similarity import jaccard_similarity
from cf_module.data.adapter import get_db_dataset
from cf_module.models import (
    FoodKind,
    SearchSession,
    RecommendationResult,
    RecommendationResponse,
)


# 실 DB (recommend.db) 기반. 합성 데이터는 cf_module/data/synthetic.py 에 보존.
# 풀: Food 296 kind / RecommendationSession 192 세션 / User 24명.
_KINDS: list[FoodKind]
_SESSIONS: list[SearchSession]
_KINDS, _SESSIONS = get_db_dataset()


def _get_user_final_selected_kinds(user_id: int) -> set[int]:
    """
    사용자가 final_select한 kind_id 집합을 반환.

    click만 한 메뉴는 관심 표현일 뿐 최종 결정이 아니므로 제외하지 않는다.
    """
    final_selected_kind_ids: set[int] = set()

    for session in _SESSIONS:
        if session.user_id != user_id:
            continue
        for action in session.actions:
            if action.action_type == "final_select":
                final_selected_kind_ids.add(action.kind_id)

    return final_selected_kind_ids


def _get_user_acted_kinds(user_id: int) -> set[int]:
    """
    해당 사용자가 click 또는 final_select한 모든 kind_id 집합을 반환.

    click과 final_select를 구분하지 않고 둘 다 "행동한 메뉴"로 본다.
    유사 사용자 선정에서는 행동 강도를 무시하고 0/1 집합으로만 비교한다.
    """
    acted_kinds: set[int] = set()

    for session in _SESSIONS:
        if session.user_id != user_id:
            continue
        for action in session.actions:
            acted_kinds.add(action.kind_id)

    return acted_kinds


def _find_similar_users(
    user_id: int,
    min_similarity: float = 0.1,
    max_users: int = 20
) -> list[tuple[int, float]]:
    """
    나와 행동 이력이 닮은 사용자를 선정.

    내 행동 메뉴 집합과 다른 사용자의 행동 메뉴 집합을 Jaccard 유사도로
    비교한다. 유사도 계산에는 행동 가중치를 쓰지 않고, 가중치는 이후
    STEP 2 점수 계산에서만 사용한다.

    Returns:
        [(user_id, similarity), ...] 형태의 리스트. 유사도 내림차순이며,
        동점은 user_id 오름차순이다. 내 행동 이력이 없으면 빈 리스트.
    """
    my_acted_kinds = _get_user_acted_kinds(user_id)
    if not my_acted_kinds or max_users <= 0:
        return []

    acted_kinds_by_user: dict[int, set[int]] = defaultdict(set)
    for session in _SESSIONS:
        if session.user_id == user_id:
            continue
        for action in session.actions:
            acted_kinds_by_user[session.user_id].add(action.kind_id)

    similar_users: list[tuple[int, float]] = []
    for other_user_id, other_acted_kinds in acted_kinds_by_user.items():
        similarity = jaccard_similarity(my_acted_kinds, other_acted_kinds)
        if similarity < min_similarity:
            continue
        similar_users.append((other_user_id, similarity))

    similar_users.sort(key=lambda item: (-item[1], item[0]))
    return similar_users[:max_users]


def _get_user_final_selected_only(user_id: int) -> set[int]:
    """
    해당 사용자가 final_select한 kind_id 집합만 반환.

    click은 제외한다. final_select는 실제로 먹기로 결정한 메뉴이므로 다시
    추천하지 않고, click만 한 메뉴는 후보로 남긴다.
    """
    final_selected: set[int] = set()

    for session in _SESSIONS:
        if session.user_id != user_id:
            continue
        for action in session.actions:
            if action.action_type == "final_select":
                final_selected.add(action.kind_id)

    return final_selected


def _filter_candidate_kinds(
    input_tags: list[str],
    user_id: int
) -> list[FoodKind]:
    """
    추천 후보 자격이 있는 kind만 반환.

    입력 태그가 1~2개면 모두 포함해야 하고, 3개 이상이면 N-1개 이상
    포함해야 한다. 사용자가 이미 final_select한 kind는 제외한다.
    click만 한 kind는 제외하지 않는다.
    """
    if not input_tags:
        return []

    input_tag_set = set(input_tags)
    required_matches = (
        len(input_tag_set)
        if len(input_tag_set) <= 2
        else len(input_tag_set) - 1
    )
    final_selected = _get_user_final_selected_only(user_id)
    candidates: list[FoodKind] = []

    for kind in _KINDS:
        if kind.kind_id in final_selected:
            continue
        matched_count = len(input_tag_set & set(kind.tags))
        if matched_count < required_matches:
            continue
        candidates.append(kind)

    return candidates


def _get_user_kind_max_weight(user_id: int, kind_id: int) -> int:
    """
    해당 사용자가 특정 kind에 한 행동 중 최대 가중치를 반환.

    사용자의 모든 세션을 통틀어 본다. click=1, final_select=2이며,
    해당 kind를 건드린 적이 없으면 0을 반환한다.
    """
    max_weight = 0

    for session in _SESSIONS:
        if session.user_id != user_id:
            continue
        for action in session.actions:
            if action.kind_id != kind_id:
                continue
            max_weight = max(max_weight, action.weight)

    return max_weight


def _score_candidates(
    candidates: list[FoodKind],
    similar_users: list[tuple[int, float]]
) -> list[tuple[FoodKind, float]]:
    """
    후보 메뉴별 개인화 CF 점수를 계산.

    각 후보 점수는 유사 사용자별 `similarity * max_action_weight`의 합이다.
    한 사용자는 한 메뉴에 대해 최대 2점까지만 기여한다. 점수가 0인 후보는
    개인화 추천 근거가 없으므로 결과에서 제외한다.
    """
    scored_candidates: list[tuple[FoodKind, float]] = []

    for kind in candidates:
        score = 0.0

        for similar_user_id, similarity in similar_users:
            max_weight = _get_user_kind_max_weight(similar_user_id, kind.kind_id)
            if max_weight == 0:
                continue
            score += similarity * max_weight

        if score > 0:
            scored_candidates.append((kind, score))

    return scored_candidates


def _get_kind_max_weights_in_session(session: SearchSession) -> dict[int, int]:
    """
    한 세션 안에서 각 kind의 최대 행동 가중치를 반환.

    같은 kind에 click(1)과 final_select(2)가 모두 있으면 2만 사용한다.
    """
    kind_weights: dict[int, int] = {}

    for action in session.actions:
        current_weight = kind_weights.get(action.kind_id, 0)
        kind_weights[action.kind_id] = max(current_weight, action.weight)

    return kind_weights


def recommend(
    input_tags: list[str],
    user_id: int,
    top_k: int = 10
) -> RecommendationResponse:
    """
    두 탭의 추천 결과를 함께 반환.

    탭 1 (기본추천): 비슷한 검색 의도의 세션을 기반으로 추천한다.
    탭 2 (개인화추천): 사용자 기반 CF. 이번 구조 재편 단계에서는 빈 리스트로
    두고, 다음 단계에서 본 로직을 구현한다.

    tab2_empty_reason 값:
    - None: 현재 단계에서는 탭 2 빈 상태 사유를 보고하지 않음
    - "no_history": 사용자 행동 이력이 없음
    - "no_similar_users": 행동 이력은 있지만 유사 사용자가 없음
    - "no_candidates": 유사 사용자는 있지만 추천 가능한 메뉴가 없음
    """
    tab1_results = recommend_tab1_default(input_tags, user_id, top_k=top_k)
    tab2_results, tab2_empty_reason = recommend_tab2_personalized(
        input_tags,
        user_id,
        top_k=top_k,
    )

    return RecommendationResponse(
        tab1_results=tab1_results,
        tab2_results=tab2_results,
        input_tags=list(input_tags),
        user_id=user_id,
        tab2_empty_reason=tab2_empty_reason,
    )


def recommend_tab1(
    input_tags: list[str],
    user_id: int,
    top_k: int = 5
) -> list[RecommendationResult]:
    """
    [보류] 콘텐츠 기반 태그 매칭.

    기존 탭 1 구현이다. 나중에 다시 사용할 수 있도록 남겨두지만,
    현재 메인 recommend()에서는 호출하지 않는다.
    """
    if not input_tags or top_k <= 0:
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


def recommend_tab1_default(
    input_tags: list[str],
    user_id: int,
    top_k: int = 10
) -> list[RecommendationResult]:
    """
    탭 1 (기본추천): 지금 검색 의도와 비슷한 세션들이 고른 메뉴.

    기존 recommend_tab2_cf의 세션 기반 CF 로직을 이동한 함수다.
    현재 입력 태그와 과거 세션의 입력 태그를 Jaccard 유사도로 비교하고,
    유사한 세션의 행동 가중치(click=1, final_select=2)를 메뉴 점수로 누적한다.

    사용자가 이미 final_select한 메뉴는 제외한다. 기존 콘텐츠 매칭 탭과의
    겹침 제한은 새 구조에서 더 이상 필요하지 않아 제거했다.
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
    results = []

    for kind_id, score in sorted_scores:
        kind = kind_by_id.get(kind_id)
        if kind is None:
            continue

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


def recommend_tab2_personalized(
    input_tags: list[str],
    user_id: int,
    top_k: int = 10
) -> tuple[list[RecommendationResult], str | None]:
    """
    탭 2 (개인화추천): 나와 닮은 사용자들이 고른 메뉴.

    Returns:
        (추천 결과 리스트, 빈 결과 사유)
    """
    my_acted_kinds = _get_user_acted_kinds(user_id)
    if not my_acted_kinds:
        return [], "no_history"

    similar_users = _find_similar_users(user_id)
    if not similar_users:
        return [], "no_similar_users"

    candidates = _filter_candidate_kinds(input_tags, user_id)
    scored_candidates = _score_candidates(candidates, similar_users)
    if not scored_candidates:
        return [], "no_candidates"

    scored_candidates.sort(key=lambda item: (-item[1], item[0].kind_id))
    top_scored_candidates = scored_candidates[:top_k]
    results: list[RecommendationResult] = []

    for kind, score in top_scored_candidates:
        kind_tags = set(kind.tags)
        matched_tags = [tag for tag in input_tags if tag in kind_tags]
        results.append(
            RecommendationResult(
                kind_id=kind.kind_id,
                kind_name=kind.name,
                score=score,
                matched_tags=matched_tags,
                reason="나와 취향이 비슷한 사용자들이 선택한 메뉴예요",
            )
        )

    return results, None
