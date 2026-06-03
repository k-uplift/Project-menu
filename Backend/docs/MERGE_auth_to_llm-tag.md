# 병합 가이드: DB 브랜치의 로그인/인증 → llm-tag

> 목적: `DB` 브랜치에 새로 구현한 **로그인/회원가입 백엔드**를 `llm-tag`(통합 서버 브랜치)와 합칠 때
> 어디서 충돌이 나고 무엇을 연결해야 하는지 정리한다. **병합 담당자는 이 문서를 먼저 읽을 것.**
> 작성: 2026-06-04 (DB 브랜치)

---

## 1. 브랜치 관계 (중요)

- 인증 작업 **이전**: `DB ⊆ llm-tag` 였다(llm-tag가 DB의 모든 커밋 포함) → 그땐 fast-forward, 충돌 0.
- 인증 작업 **이후**: DB에 llm-tag엔 없는 인증 커밋이 생겨 **분기(divergence)** 발생 → 이제부터는 **3-way 병합**이고, 아래 §4 한 곳에서 충돌이 난다.

---

## 2. 이 브랜치가 추가한 것

순수 신규 인증 기능. **llm-tag에는 로그인/회원가입 엔드포인트가 전혀 없다**(api.py엔 `/foods`·`/foods_cf`·`/events` 등만 존재, `verify_password`는 어디서도 호출 안 됨).

| 파일 | 내용 | 비고 |
|---|---|---|
| `src/auth/tokens.py` | 무상태 HMAC-SHA256 서명 토큰 발급/검증 | stdlib만, **DB 스키마 변경 없음** |
| `src/auth/service.py` | `signup()` / `login()` 순수 로직 | `password.py`·User 테이블 재사용, 웹프레임워크 비의존 |
| `src/auth/routes.py` | FastAPI 라우터: `POST /auth/signup`·`/login`, `GET /auth/me` | `include_router` 로 흡수 가능하게 분리 |
| `auth_app.py` | 단독 실행용 앱 | llm-tag의 `api.py`와 **파일명 분리** |
| `requirements.txt` | fastapi / uvicorn[standard] / pydantic 추가 | ⚠️ §4 충돌 |
| `src/data/database/schema.py` | `DB_PATH` 를 `RECOMMEND_DB_PATH` 환경변수로 오버라이드 가능하게 | §6 |

---

## 3. 파일별 충돌 진단

| 파일 | llm-tag도 수정? | 충돌 | 처리 |
|---|---|---|---|
| `src/auth/*`, `auth_app.py` | ❌ (신규 경로) | **없음** | 그대로 들어옴 |
| `src/data/database/schema.py` | ❌ (llm-tag 미수정) | **없음** | `DB_PATH` 변경만 존재 (§6) |
| `requirements.txt` | ✅ (끝줄에 의존성 추가) | **충돌 1건** | §4 복붙으로 해소 |

---

## 4. requirements.txt 충돌 해소 (복붙용)

양쪽 모두 `pyproj>=3.6` **다음 줄**에 의존성을 추가해서 git이 자동 병합하지 못한다.
충돌 마커가 보이면, 양쪽 추가분의 **합집합**으로 바꾸면 된다. 아래 블록을 그대로 쓸 것:

```text
requests>=2.31
python-dotenv>=1.0
playwright>=1.40
pyproj>=3.6

# LLM 태그 추출/메뉴 enrichment (src/llm) — llm-tag
anthropic>=0.40

# 인증 + 추천 API 서버 (auth_app.py·api.py / src/auth)
fastapi>=0.110
uvicorn[standard]>=0.27   # [standard] 가 llm-tag 의 plain uvicorn 상위호환
pydantic>=2
```

- `fastapi` 버전은 양쪽 동일(`>=0.110`).
- `uvicorn` 은 **`uvicorn[standard]` 채택**(llm-tag의 `uvicorn>=0.27` 을 포함하므로 안전).
- `anthropic`(llm-tag) 와 `pydantic`(DB) 는 서로 겹치지 않으니 **둘 다 남긴다**.

---

## 5. 병합 후 필수 연결 작업 — 엔드포인트 노출

병합만 하면 인증 코드는 들어오지만, **통합 서버(`api.py`)에 라우트가 자동으로 붙지는 않는다.**
`api.py` 에 아래 두 줄을 추가해야 `/auth/*` 엔드포인트가 통합 서버에 노출된다.

```python
# api.py 상단 import 부근
from src.auth.routes import router as auth_router

# app = FastAPI(...) 정의 직후
app.include_router(auth_router)
```

- 연결 후 엔드포인트: `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`.
- 연결하지 않고 `auth_app.py` 를 따로 띄워도 동작은 한다(연결은 "하나의 서버로 합칠 때"만 필요).
- 합친 뒤 단독 실행 파일 `auth_app.py` 는 제거하거나 개발용으로 남겨도 무방.

---

## 6. schema.py — DB_PATH 환경변수화 (비파괴적)

```python
DB_PATH = Path(os.environ.get("RECOMMEND_DB_PATH", BACKEND_ROOT / "db" / "recommend.db"))
```

- **기본값은 기존과 동일**(`db/recommend.db`) → llm-tag의 seed/adapter/api 동작에 영향 없음.
- 테스트/스테이징에서만 `RECOMMEND_DB_PATH` 로 다른 파일을 가리킬 수 있게 한 추가 기능.
- llm-tag는 schema.py를 건드리지 않았으므로 **충돌 없이** 들어온다.

---

## 7. 운영 주의 — AUTH_SECRET

`src/auth/tokens.py` 의 서명 비밀키 기본값은 **개발용**이다:

```python
_SECRET = os.environ.get("AUTH_SECRET", "dev-insecure-secret-change-me")
```

- **배포 전 `AUTH_SECRET` 환경변수를 반드시 설정**할 것(미설정 시 토큰 위조 가능).
- 비밀키를 바꾸면 그 전에 발급된 토큰은 모두 무효화된다(재로그인 필요) — 정상 동작.

---

## 8. 병합 후 검증 체크리스트

```bash
cd Backend
# (통합 서버) uvicorn api:app --port 8000   또는  (단독) uvicorn auth_app:app --port 8000

# 데모 유저 로그인 (비번 demo1234)
curl -X POST localhost:8000/auth/login -H "Content-Type: application/json" \
     -d '{"email":"t1_u1@demo","password":"demo1234"}'
# → 200 {user, token}

# 토큰으로 본인 확인
curl localhost:8000/auth/me -H "Authorization: Bearer <token>"
# → 200 {user}
```

검증된 동작: 로그인 성공/실패(401), 회원가입(201)/중복(409)/형식오류(400), 토큰 위조·만료 거부, `/me` 인증.

---

## 9. ⚠️ 별개지만 같이 주의 — recommend.db (바이너리)

인증과 무관하지만, **llm-tag 병합 시 가장 큰 함정**이라 함께 적는다.

- `Backend/db/recommend.db` 는 바이너리라 git 3-way 병합이 안 된다 → **한쪽이 통째로 채택**된다.
- llm-tag본(로그 768·세션 808·Badge 29, user_id 1~24)이 DB본(로그 192·세션 192, user_id 25~48)을 **덮어쓴다**.
- 그 결과 **데모 유저의 user_id가 25~48 → 1~24 로 바뀐다.** user_id를 하드코딩한 코드/문서가 있으면 점검할 것.
- 인증 로직 자체는 email 기준이라 영향 없음(로그인은 email로 조회).
- llm-tag본엔 **로그 없는 빈 세션 40개**(수동 테스트 흔적, session_id 769~808)가 섞여 있다. 필요 시 정리:
  ```sql
  DELETE FROM RecommendationSession
   WHERE session_id NOT IN (SELECT session_id FROM UserInteractionLog);
  ```
