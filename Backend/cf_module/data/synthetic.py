from collections import Counter

from cf_module.models import FoodKind, MenuAction, SearchSession


CATEGORY_KIND_SPECS = [
    (
        "한식 국물탕",
        [
            ("김치찌개", ["얼큰한", "국물있는", "든든한", "해장"]),
            ("된장찌개", ["국물있는", "담백한", "든든한", "따뜻한"]),
            ("순두부찌개", ["국물있는", "담백한", "따뜻한", "든든한"]),
            ("육개장", ["얼큰한", "국물있는", "따뜻한", "해장"]),
            ("부대찌개", ["얼큰한", "국물있는", "든든한", "진한"]),
            ("감자탕", ["얼큰한", "국물있는", "든든한", "해장"]),
            ("해장국", ["얼큰한", "국물있는", "해장", "따뜻한"]),
            ("콩나물국밥", ["국물있는", "담백한", "해장", "따뜻한"]),
        ],
    ),
    (
        "한식 고기",
        [
            ("삼겹살", ["고소한", "든든한", "담백한"]),
            ("목살", ["고소한", "든든한", "담백한"]),
            ("갈비", ["달달한", "든든한", "진한"]),
            ("차돌박이", ["고소한", "든든한", "진한"]),
            ("제육볶음", ["얼큰한", "든든한", "진한"]),
            ("보쌈", ["고소한", "담백한", "든든한"]),
            ("족발", ["고소한", "든든한", "진한"]),
            ("곱창", ["고소한", "진한", "든든한"]),
        ],
    ),
    (
        "한식 면밥",
        [
            ("냉면", ["시원한", "담백한", "국물있는"]),
            ("비빔밥", ["든든한", "가벼운", "담백한"]),
            ("볶음밥", ["고소한", "든든한", "진한"]),
            ("김밥", ["가벼운", "담백한"]),
            ("칼국수", ["국물있는", "담백한", "따뜻한", "든든한"]),
            ("잔치국수", ["국물있는", "담백한", "따뜻한", "가벼운"]),
        ],
    ),
    (
        "일식",
        [
            ("초밥", ["담백한", "가벼운", "시원한"]),
            ("회", ["담백한", "가벼운", "시원한"]),
            ("우동", ["국물있는", "담백한", "따뜻한"]),
            ("돈까스", ["바삭한", "든든한", "고소한", "얼큰한"]),
            ("라멘", ["국물있는", "진한", "따뜻한", "든든한"]),
            ("규동", ["든든한", "진한", "달달한"]),
        ],
    ),
    (
        "중식",
        [
            ("짬뽕", ["얼큰한", "국물있는", "진한", "따뜻한"]),
            ("짜장면", ["진한", "든든한", "달달한"]),
            ("탕수육", ["바삭한", "달달한", "고소한"]),
            ("마라탕", ["얼큰한", "국물있는", "진한", "야식"]),
            ("마파두부", ["얼큰한", "진한", "든든한"]),
        ],
    ),
    (
        "양식",
        [
            ("피자", ["든든한", "진한", "고소한"]),
            ("파스타", ["든든한", "진한", "담백한"]),
            ("버거", ["든든한", "진한", "고소한"]),
            ("샐러드", ["가벼운", "담백한", "시원한"]),
            ("샌드위치", ["가벼운", "담백한"]),
        ],
    ),
    (
        "디저트",
        [
            ("케이크", ["달달한", "진한"]),
            ("마카롱", ["달달한", "바삭한"]),
            ("와플", ["달달한", "바삭한", "고소한"]),
            ("아이스크림", ["달달한", "시원한", "고소한", "바삭한"]),
        ],
    ),
    (
        "치킨",
        [
            ("후라이드", ["바삭한", "고소한", "든든한", "야식"]),
            ("양념치킨", ["달달한", "얼큰한", "바삭한", "야식"]),
            ("강정", ["달달한", "바삭한", "야식"]),
        ],
    ),
    (
        "분식",
        [
            ("떡볶이", ["얼큰한", "쫄깃한", "야식", "진한"]),
            ("순대", ["든든한", "진한"]),
            ("튀김", ["바삭한", "고소한", "야식"]),
            ("라면", ["얼큰한", "국물있는", "야식", "따뜻한"]),
            ("비빔국수", ["얼큰한", "쫄깃한", "시원한"]),
        ],
    ),
]


PERSONA_SPECS = [
    {
        "user_ids": range(1, 8),
        "main_inputs": [("얼큰한", "야식"), ("국물있는", "든든한"), ("얼큰한", "해장")],
        "variant_inputs": [("바삭한", "달달한")],
        "final_names": ["김치찌개", "부대찌개", "감자탕", "짬뽕"],
        "click_names": ["해장국", "라면", "마라탕"],
    },
    {
        "user_ids": range(8, 14),
        "main_inputs": [("든든한", "고소한"), ("진한", "달달한"), ("든든한", "담백한")],
        "variant_inputs": [("시원한", "가벼운")],
        "final_names": ["제육볶음", "갈비", "피자", "짜장면"],
        "click_names": ["삼겹살", "버거", "볶음밥"],
    },
    {
        "user_ids": range(14, 20),
        "main_inputs": [("담백한", "시원한"), ("가벼운", "국물있는"), ("담백한", "따뜻한")],
        "variant_inputs": [("얼큰한", "야식")],
        "final_names": ["비빔밥", "김밥", "초밥", "샐러드"],
        "click_names": ["회", "샌드위치", "잔치국수"],
    },
    {
        "user_ids": range(20, 26),
        "main_inputs": [("야식", "바삭한"), ("얼큰한", "쫄깃한"), ("야식", "국물있는")],
        "variant_inputs": [("담백한", "가벼운")],
        "final_names": ["떡볶이", "라면", "양념치킨", "마라탕"],
        "click_names": ["튀김", "강정", "후라이드"],
    },
    {
        "user_ids": range(26, 32),
        "main_inputs": [("해장", "따뜻한"), ("국물있는", "얼큰한"), ("해장", "담백한")],
        "variant_inputs": [("달달한", "바삭한")],
        "final_names": ["해장국", "콩나물국밥", "육개장", "감자탕"],
        "click_names": ["김치찌개", "순두부찌개", "라면"],
    },
    {
        "user_ids": range(32, 38),
        "main_inputs": [("달달한", "고소한"), ("바삭한", "야식"), ("달달한", "시원한")],
        "variant_inputs": [("든든한", "진한")],
        "final_names": ["탕수육", "와플", "마카롱", "양념치킨"],
        "click_names": ["케이크", "강정", "아이스크림"],
    },
    {
        "user_ids": range(38, 44),
        "main_inputs": [("시원한", "담백한"), ("가벼운", "달달한"), ("시원한", "국물있는")],
        "variant_inputs": [("진한", "든든한")],
        "final_names": ["냉면", "회", "아이스크림", "비빔국수"],
        "click_names": ["초밥", "샐러드", "김밥"],
    },
    {
        "user_ids": range(44, 51),
        "main_inputs": [("고소한", "든든한"), ("따뜻한", "국물있는"), ("고소한", "바삭한")],
        "variant_inputs": [("시원한", "달달한")],
        "final_names": ["삼겹살", "우동", "돈까스", "칼국수"],
        "click_names": ["목살", "라멘", "튀김"],
    },
]


def generate_synthetic_kinds() -> list[FoodKind]:
    """50개 kind 생성."""
    kinds = []
    kind_id = 1

    for _, items in CATEGORY_KIND_SPECS:
        for name, tags in items:
            kinds.append(FoodKind(kind_id=kind_id, name=name, tags=list(tags)))
            kind_id += 1

    return kinds


def generate_synthetic_sessions(kinds: list[FoodKind]) -> list[SearchSession]:
    """50명 페르소나의 200개 세션 생성."""
    kind_by_name = {kind.name: kind for kind in kinds}
    sessions = []
    session_id = 1

    for persona in PERSONA_SPECS:
        main_inputs = persona["main_inputs"]
        variant_inputs = persona["variant_inputs"]
        final_names = persona["final_names"]
        click_names = persona["click_names"]

        for user_id in persona["user_ids"]:
            for session_index in range(4):
                if session_index < 3:
                    input_tags = list(main_inputs[(user_id + session_index) % len(main_inputs)])
                else:
                    input_tags = list(variant_inputs[(user_id + session_index) % len(variant_inputs)])

                final_name = final_names[(user_id + session_index) % len(final_names)]
                first_click = click_names[(user_id + session_index) % len(click_names)]
                second_click = final_names[(user_id + session_index + 1) % len(final_names)]

                actions = [MenuAction(kind_id=kind_by_name[first_click].kind_id, action_type="click")]
                if second_click != first_click and second_click != final_name:
                    actions.append(MenuAction(kind_id=kind_by_name[second_click].kind_id, action_type="click"))
                actions.append(MenuAction(kind_id=kind_by_name[final_name].kind_id, action_type="final_select"))

                sessions.append(
                    SearchSession(
                        session_id=session_id,
                        user_id=user_id,
                        input_tags=input_tags,
                        actions=actions,
                        timestamp="2024-01-01T12:00:00",
                    )
                )
                session_id += 1

    return sessions


def get_synthetic_dataset() -> tuple[list[FoodKind], list[SearchSession]]:
    """전체 합성 데이터 반환. 메인 진입점."""
    kinds = generate_synthetic_kinds()
    sessions = generate_synthetic_sessions(kinds)
    return kinds, sessions


def get_category_counts() -> dict[str, int]:
    """검증용 카테고리별 kind 수 통계 반환."""
    return {category: len(items) for category, items in CATEGORY_KIND_SPECS}


def get_dataset_summary(
    kinds: list[FoodKind],
    sessions: list[SearchSession],
) -> dict[str, object]:
    """합성 데이터 품질을 빠르게 확인하기 위한 인메모리 요약."""
    kind_by_id = {kind.kind_id: kind for kind in kinds}
    final_select_counts = Counter()
    input_tag_counts = Counter()
    mismatched_count = 0

    for session in sessions:
        input_tags = set(session.input_tags)
        input_tag_counts.update(session.input_tags)

        final_actions = [action for action in session.actions if action.action_type == "final_select"]
        if not final_actions:
            continue

        final_kind = kind_by_id[final_actions[-1].kind_id]
        final_select_counts[final_kind.name] += 1
        if not input_tags.issubset(set(final_kind.tags)):
            mismatched_count += 1

    mismatch_ratio = mismatched_count / len(sessions) if sessions else 0.0

    return {
        "kind_count": len(kinds),
        "user_count": len({session.user_id for session in sessions}),
        "session_count": len(sessions),
        "category_counts": get_category_counts(),
        "top_selected_kinds": final_select_counts.most_common(5),
        "input_tag_counts": dict(input_tag_counts.most_common()),
        "mismatch_ratio": mismatch_ratio,
    }
