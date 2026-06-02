import os
import sys
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cf_module.core.actions import create_search_session, record_final_select
from cf_module.core.recommend import (
    _get_user_final_selected_only,
    recommend,
    recommend_tab2_personalized,
)
from cf_module.core import recommend as recommend_module


SPICY_SOUP = ["얼큰한", "국물있는"]
LIGHT_CLEAN = ["담백한", "가벼운"]


def _new_user_id() -> int:
    """Return a user id that is not in the in-memory session dataset."""
    existing = {session.user_id for session in recommend_module._SESSIONS}
    return max(existing, default=0) + 100_000


def test_tab1_default_works():
    """탭 1 기본추천은 신규 사용자에게도 결과를 낸다."""
    response = recommend(SPICY_SOUP, user_id=99999, top_k=10)

    assert len(response.tab1_results) > 0
    assert response.tab2_results == []
    assert response.tab2_empty_reason == "no_history"
    assert any(score != float(int(score)) for score in [r.score for r in response.tab1_results])


def test_tab2_personalized_works():
    """탭 2는 행동 이력이 있는 사용자에게 개인화 추천을 낸다."""
    response = recommend(SPICY_SOUP, user_id=1, top_k=10)

    assert len(response.tab2_results) > 0
    assert response.tab2_empty_reason is None
    for result in response.tab2_results:
        assert result.reason
        assert result.score > 0


def test_personalization_same_input_different_user():
    """같은 입력이라도 사용자가 다르면 탭 2 추천이 달라진다."""
    input_tags = ["국물있는"]
    user_1_results, user_1_reason = recommend_tab2_personalized(input_tags, user_id=1, top_k=10)
    user_14_results, user_14_reason = recommend_tab2_personalized(input_tags, user_id=14, top_k=10)

    print("user 1:", [result.kind_name for result in user_1_results])
    print("user 14:", [result.kind_name for result in user_14_results])

    assert user_1_reason is None
    assert user_14_reason is None
    assert [result.kind_id for result in user_1_results] != [
        result.kind_id for result in user_14_results
    ]


def test_tab2_no_history():
    """행동 이력이 없는 사용자는 no_history와 빈 결과를 받는다."""
    results, reason = recommend_tab2_personalized(["얼큰한"], user_id=99999, top_k=10)

    assert results == []
    assert reason == "no_history"


def test_tab2_empty_reasons():
    """탭 2 빈 결과 사유를 구분한다."""
    no_history_results, no_history_reason = recommend_tab2_personalized(
        ["얼큰한"], user_id=99999
    )
    assert no_history_results == []
    assert no_history_reason == "no_history"

    no_similar_user = _new_user_id()
    session_id = create_search_session(no_similar_user, SPICY_SOUP)
    record_final_select(session_id, kind_id=999_999)
    no_similar_results, no_similar_reason = recommend_tab2_personalized(
        SPICY_SOUP, user_id=no_similar_user
    )
    assert no_similar_results == []
    assert no_similar_reason == "no_similar_users"

    no_candidate_results, no_candidate_reason = recommend_tab2_personalized(
        ["시원한"], user_id=1
    )
    assert no_candidate_results == []
    assert no_candidate_reason == "no_candidates"


def test_two_tabs_differ():
    """탭 1과 탭 2는 서로 다른 추천 방식을 쓴다."""
    response = recommend(SPICY_SOUP, user_id=1, top_k=10)

    tab1_ids = {result.kind_id for result in response.tab1_results}
    tab2_ids = {result.kind_id for result in response.tab2_results}

    assert tab1_ids
    assert tab2_ids
    assert tab1_ids != tab2_ids


def test_tab2_excludes_my_final_select():
    """탭 2는 내가 final_select한 메뉴를 추천하지 않는다."""
    final_selected = _get_user_final_selected_only(1)
    results, reason = recommend_tab2_personalized(SPICY_SOUP, user_id=1, top_k=10)
    result_ids = {result.kind_id for result in results}

    assert reason is None
    assert final_selected.isdisjoint(result_ids)


def test_action_changes_recommendation():
    """행동 이력이 생기면 no_history 상태를 벗어난다."""
    user_id = _new_user_id()

    _, reason_before = recommend_tab2_personalized(SPICY_SOUP, user_id, top_k=10)
    session_id = create_search_session(user_id, SPICY_SOUP)
    record_final_select(session_id, kind_id=1)
    _, reason_after = recommend_tab2_personalized(SPICY_SOUP, user_id, top_k=10)

    print(f"before: {reason_before}, after: {reason_after}")
    assert reason_before == "no_history"
    assert reason_after != "no_history"


def test_input_immutability():
    """응답의 input_tags를 수정해도 원본 입력은 바뀌지 않는다."""
    original = list(SPICY_SOUP)
    response = recommend(original, user_id=1, top_k=10)

    response.input_tags.append("야식")
    assert "야식" not in original


TEST_FUNCTIONS = [
    test_tab1_default_works,
    test_tab2_personalized_works,
    test_personalization_same_input_different_user,
    test_tab2_no_history,
    test_tab2_empty_reasons,
    test_two_tabs_differ,
    test_tab2_excludes_my_final_select,
    test_action_changes_recommendation,
    test_input_immutability,
]


def load_tests(loader, tests, pattern):
    """Allow python -m unittest to run these function-style tests."""
    suite = unittest.TestSuite()
    for test_function in TEST_FUNCTIONS:
        suite.addTest(unittest.FunctionTestCase(test_function))
    return suite


if __name__ == "__main__":
    for test_function in TEST_FUNCTIONS:
        test_function()
    print("모든 테스트 통과")
