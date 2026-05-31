import os
import sys
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cf_module.core.actions import (
    create_search_session,
    record_click,
    record_final_select,
)
from cf_module.core.recommend import recommend


def test_new_user_first_search():
    """
    행동 기록 없는 신규 사용자가 검색했을 때:
    - 두 탭 모두 결과가 나옴
    - 결과는 비어있지 않음
    - 두 탭의 결과가 서로 다름 (탭 분리 효과)
    """
    response = recommend(["얼큰한", "국물있는"], user_id=9999, top_k=5)

    assert len(response.tab1_results) > 0
    assert len(response.tab2_results) > 0

    tab1_ids = {result.kind_id for result in response.tab1_results}
    tab2_ids = {result.kind_id for result in response.tab2_results}
    assert tab1_ids != tab2_ids


def test_different_inputs_give_different_results():
    """다른 입력은 다른 추천을 만든다."""
    response_a = recommend(["얼큰한", "국물있는"], user_id=9999, top_k=5)
    response_b = recommend(["담백한", "가벼운"], user_id=9999, top_k=5)

    tab1_a = {result.kind_id for result in response_a.tab1_results}
    tab1_b = {result.kind_id for result in response_b.tab1_results}

    assert tab1_a.isdisjoint(tab1_b) or len(tab1_a & tab1_b) < 2


def test_action_recording_excludes_seen_menu():
    """행동 기록 후 본인이 final_select한 메뉴는 다음 추천에서 제외."""
    user_id = 9998
    input_tags = ["얼큰한", "국물있는"]

    before = recommend(input_tags, user_id, top_k=5)
    before_tab1_ids = {result.kind_id for result in before.tab1_results}
    assert len(before_tab1_ids) > 0

    first_kind_id = before.tab1_results[0].kind_id

    session_id = create_search_session(user_id, input_tags)
    record_click(session_id, first_kind_id)
    record_final_select(session_id, first_kind_id)

    after = recommend(input_tags, user_id, top_k=5)
    after_tab1_ids = {result.kind_id for result in after.tab1_results}

    assert first_kind_id not in after_tab1_ids


def test_tab_overlap_handling():
    """탭 1 상위 3개와 탭 2의 겹침은 최대 1개."""
    response = recommend(["얼큰한", "국물있는"], user_id=9997, top_k=5)

    tab1_top3 = [result.kind_id for result in response.tab1_results[:3]]
    tab2_ids = [result.kind_id for result in response.tab2_results]

    overlap = [kind_id for kind_id in tab2_ids if kind_id in tab1_top3]
    assert len(overlap) <= 1, f"Overlap too high: {overlap}"


def test_tab1_vs_tab2_different_logic():
    """
    탭 1과 탭 2는 다른 알고리즘을 사용하므로
    같은 입력에 대해 다른 점수 패턴을 보인다.
    """
    response = recommend(["얼큰한", "국물있는"], user_id=9996, top_k=5)

    tab1_scores = [result.score for result in response.tab1_results]
    tab2_scores = [result.score for result in response.tab2_results]

    for score in tab1_scores:
        assert score == float(int(score))

    assert any(score != float(int(score)) for score in tab2_scores), (
        "탭 2 점수가 모두 정수면 CF 작동 의심"
    )


def test_cold_start():
    """매칭이 거의 없는 입력에도 에러 없이 동작."""
    response = recommend(["바삭한"], user_id=9995, top_k=5)

    assert isinstance(response.tab1_results, list)
    assert isinstance(response.tab2_results, list)


def test_input_immutability():
    """응답을 수정해도 원본 입력은 안 바뀐다."""
    original_input = ["얼큰한", "국물있는"]
    response = recommend(original_input, user_id=9994, top_k=5)

    response.input_tags.append("야식")
    assert "야식" not in original_input


def test_full_user_journey():
    """
    실제 시연 시나리오:
    1. 첫 검색
    2. 추천 메뉴 클릭
    3. 최종선택
    4. 다른 입력으로 두 번째 검색
    5. 결과가 적절히 변화하는지 확인
    """
    user_id = 9993

    response_1 = recommend(["얼큰한", "국물있는"], user_id, top_k=5)
    assert len(response_1.tab1_results) > 0

    first_kind = response_1.tab1_results[0]
    session_id_1 = create_search_session(user_id, ["얼큰한", "국물있는"])
    record_click(session_id_1, first_kind.kind_id)

    record_final_select(session_id_1, first_kind.kind_id)

    response_2 = recommend(["담백한", "가벼운"], user_id, top_k=5)
    assert len(response_2.tab1_results) > 0

    response_3 = recommend(["얼큰한", "국물있는"], user_id, top_k=5)
    response_3_ids = {result.kind_id for result in response_3.tab1_results}
    assert first_kind.kind_id not in response_3_ids


TEST_FUNCTIONS = [
    test_new_user_first_search,
    test_different_inputs_give_different_results,
    test_action_recording_excludes_seen_menu,
    test_tab_overlap_handling,
    test_tab1_vs_tab2_different_logic,
    test_cold_start,
    test_input_immutability,
    test_full_user_journey,
]


def load_tests(loader, tests, pattern):
    """python -m unittest에서도 함수형 테스트를 실행할 수 있게 연결."""
    suite = unittest.TestSuite()
    for test_function in TEST_FUNCTIONS:
        suite.addTest(unittest.FunctionTestCase(test_function))
    return suite


if __name__ == "__main__":
    for test_function in TEST_FUNCTIONS:
        test_function()
    print("모든 테스트 통과")
