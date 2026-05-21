"""LLM 태그 추출/매칭 패키지.

import 시 Backend/.env를 자동 로드 → .env에 ANTHROPIC_API_KEY만 넣으면
별도 export 없이 Claude 호출이 동작한다. python-dotenv 미설치 시 조용히 건너뛴다
(그 경우 export로 환경변수를 주면 됨).
"""

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass
