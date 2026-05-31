"""태그 집합 간 유사도 계산 도구.

단순 교집합 개수만 쓰면 태그가 많은 세션이 유리해질 수 있다.
예를 들어 입력이 ["얼큰한", "국물있는"]일 때,
세션 A ["얼큰한", "국물있는"]와 세션 B
["얼큰한", "국물있는", "든든한", "야식", "해장"]는
교집합 개수가 모두 2다.

하지만 A는 정확히 같은 의도이고, B는 더 넓은 의도다.
Jaccard는 |A ∩ B| / |A ∪ B|로 정규화해 태그 수의 영향을 줄인다.
"""


def jaccard_similarity(tags_a: set[str], tags_b: set[str]) -> float:
    """
    두 태그 집합의 Jaccard 유사도 계산.

    공식: |A ∩ B| / |A ∪ B|

    Args:
        tags_a: 첫 번째 태그 집합. list/tuple 등 iterable도 허용.
        tags_b: 두 번째 태그 집합. list/tuple 등 iterable도 허용.

    Returns:
        0.0 ~ 1.0 사이의 유사도 값.
        두 집합이 모두 비어있거나, 한쪽이 비어있으면 0.0 반환.

    사용 맥락:
        탭 2 CF에서 "현재 입력 태그"와 "과거 세션의 입력 태그"의
        유사도를 측정. 태그 수에 영향받지 않고 정확한 매칭을 평가.
    """
    normalized_a = set(tags_a)
    normalized_b = set(tags_b)

    if not normalized_a or not normalized_b:
        return 0.0

    intersection = normalized_a & normalized_b
    union = normalized_a | normalized_b
    return len(intersection) / len(union)
