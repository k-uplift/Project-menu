from cf_module.core import recommend as _recommend_module
from cf_module.models import MenuAction, SearchSession


def _find_session(session_id: int) -> SearchSession:
    """session_id로 인메모리 세션을 조회."""
    for session in _recommend_module._SESSIONS:
        if session.session_id == session_id:
            return session
    raise ValueError(f"Unknown session_id: {session_id}")


def create_search_session(
    user_id: int,
    input_tags: list[str],
    timestamp: str = ""
) -> int:
    """
    새 검색 세션 생성.

    호출 시점: 사용자가 검색을 시작할 때 (LLM이 태그 추출한 직후).

    처리:
    1. 새 session_id 발급 (기존 session_id 중 max + 1)
    2. SearchSession 객체 생성 (actions는 빈 리스트로 시작)
    3. _SESSIONS에 추가
    4. 새 session_id 반환

    Args:
        user_id: 사용자 식별자
        input_tags: LLM이 추출한 태그 (14개 중 일부)
        timestamp: 생성 시각 문자열 (기본값 "")

    Returns:
        새로 생성된 session_id

    Raises:
        ValueError: input_tags가 비어있을 때
    """
    if not input_tags:
        raise ValueError("input_tags must not be empty")

    next_session_id = max(
        (session.session_id for session in _recommend_module._SESSIONS),
        default=0,
    ) + 1

    session = SearchSession(
        session_id=next_session_id,
        user_id=user_id,
        input_tags=list(input_tags),
        timestamp=timestamp,
    )
    _recommend_module._SESSIONS.append(session)
    return next_session_id


def record_click(session_id: int, kind_id: int) -> None:
    """
    세션 내 메뉴 클릭 기록.

    호출 시점: 사용자가 추천 결과에서 메뉴를 클릭했을 때.

    처리:
    1. session_id로 세션 조회
    2. MenuAction(kind_id, "click") 추가

    중복 정책:
    같은 세션에서 같은 kind를 여러 번 클릭해도 모두 기록.
    (점수 집계 단계에서 max weight만 카운트하므로 중복 부담 없음)

    Raises:
        ValueError: session_id가 존재하지 않을 때
    """
    session = _find_session(session_id)
    session.actions.append(MenuAction(kind_id=kind_id, action_type="click"))


def record_final_select(session_id: int, kind_id: int) -> None:
    """
    세션 내 메뉴 최종선택 기록.

    호출 시점: 사용자가 길찾기/배달 버튼을 눌렀을 때.

    처리:
    1. session_id로 세션 조회
    2. MenuAction(kind_id, "final_select") 추가

    중복 정책:
    같은 세션에서 final_select는 1회만 일어나는 게 정상이지만,
    이 함수 자체는 중복 검사하지 않음 (단순 기록 함수).
    상위 로직(API 등)에서 세션당 1회 보장.

    Raises:
        ValueError: session_id가 존재하지 않을 때
    """
    session = _find_session(session_id)
    session.actions.append(MenuAction(kind_id=kind_id, action_type="final_select"))
