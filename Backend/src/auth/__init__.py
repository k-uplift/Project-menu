"""인증(로그인/회원가입) 모듈.

  - tokens : 무상태 HMAC 서명 토큰 발급/검증 (DB 스키마 변경 없음)
  - service: signup()/login() 순수 로직 (password.py 재사용, 웹프레임워크 비의존)
  - routes : FastAPI 라우터 (추후 통합 api.py 에 include_router 로 흡수 가능)
"""
