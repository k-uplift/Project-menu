# Crawler 명세

`Backend/src/crawler/` 의 네이버 플레이스 크롤러 모듈 명세. 인허가 데이터로 정제된 가게 목록을 입력 받아, 네이버 플레이스에서 메뉴·영업시간을 수집해 `details.db` 에 저장한다.

## 입력 / 출력

| 구분 | 위치 | 내용 |
|---|---|---|
| 입력 | `Backend/db/restaurants.db` / `restaurants` 테이블 | 인허가 정제 결과 (`data/clean.py` 산출물). MGTNO, BPLCNM, 주소, X·Y 좌표 등 |
| 출력 | `Backend/db/details.db` | 네이버 매칭 결과 + 메뉴 + 영업시간 |

## 모듈 구조

```
src/crawler/
  browser.py   Playwright 브라우저 세션 wrapper
  search.py    가게명·주소·좌표 → 네이버 place_id 매칭
  detail.py    place_id → 메뉴 / 영업시간 파싱
  db.py        details.db 스키마 + 마이그레이션
  coord.py     TM(EPSG:5174) ↔ WGS84 좌표 변환, 거리 계산
  run.py       전체 파이프라인 오케스트레이션
```

## 데이터 흐름

```
restaurants.db
   │  load_source_stores()
   ▼
(MGTNO, BPLCNM, 주소, X, Y) 튜플 목록
   │
   ▼
get_existing_place_id(mgtno)  ── 있으면 검색 스킵 ──┐
   │ 없음                                          │
   ▼                                              │
parse_tm(X, Y)  → (lng, lat) WGS84                │
   │                                              │
   ▼                                              │
find_place_id(name, address, lnglat)              │
  ├─ search_place() : Naver allSearch API         │
  ├─ 위치 필터 (좌표 300m / 구·동·도로명)           │
  └─ 이름 핵심 토큰 일치                           │
   │                                              │
   ▼                                              │
place_id  ◀──────────────────────────────────────┘
   │
   ▼
fetch_detail(place_id)
  ├─ home 페이지: __APOLLO_STATE__ 파싱 → 영업시간
  │   └─ 실패 시 DOM 펼치기 + i8cJw/H3ua4 페어 추출
  └─ menu/list 페이지: __APOLLO_STATE__ 파싱 → 메뉴
   │
   ▼
upsert_store + replace_menus + replace_hours → details.db
```

## 모듈별 책임

### browser.py
- Playwright Chromium 세션을 컨텍스트 매니저로 yield (`browser_session()`).
- 봇 탐지 회피용 설정: `User-Agent` 위장, `navigator.webdriver` 숨김, 한국 로케일/타임존.
- 환경변수: `HEADLESS=0` (창 보기 / 기본 1), `SLOW_MO=300` (각 액션 사이 ms 대기 / 기본 0).

### search.py
- `search_place(query, page)` — `map.naver.com/p/search/{query}` 진입 후 `/api/search/allSearch` XHR 응답을 가로채 후보 리스트 반환.
- `find_place_id(name, page, source_address, source_lnglat)` — 매칭 의사 결정:
  1. **위치 필터**
     - `source_lnglat` 있으면: cand 의 `(lng, lat)` 와 haversine 거리 ≤ 300m 인 후보만 통과.
     - 좌표 없으면: `_matches_location()` 로 (구, 동, 도로명 베이스) 텍스트 매칭.
  2. **이름 매칭** (`_name_matches`)
     - 정규화 후 완전 일치 → 통과
     - source 핵심 토큰(접미사 `본점/분점/N호점/...` 제외) 모두가 cand 이름에 포함되어야 통과
     - 미일치 시 `None` 반환 (오매칭 방지).
- `_extract_road()` — 주소에서 도로명 베이스 토큰 추출 (`삼선교로14길` → `삼선교로`).

#### PlaceCandidate 필드
- `id`, `name`, `address`, `road_address`, `category`
- `lng`, `lat` (WGS84) — 좌표 매칭용
- `tel`, `telDisplay` — 향후 전화번호 매칭에 사용 예정

### detail.py
- `fetch_detail(place_id, page)` — home + menu/list 페이지 2회 진입.
- **APOLLO_STATE 추출 3계층**: JS 컨텍스트 `window.__APOLLO_STATE__` → HTML 내 inline → late HTML.
- **메뉴 파싱**: `__typename` 이 `*Menu*` 인 dict 중 name + price 가 있는 것 수집.
- **영업시간 파싱 우선순위**:
  1. Apollo state 의 `openingHours` / `BusinessHour` 타입
  2. XHR 응답 폴백
  3. DOM 펼치기 + i8cJw/H3ua4 페어 추출 + `_parse_time_block()` 분해
- **펼치기 (`_expand_hours_block`)**: `영업시간` 섹션 ancestor (`place_section` 클래스) 로 범위 한정. strategy 순회: 텍스트(펼쳐보기/펼치기/더보기) → `aria-expanded=false` → 일반 `role="button"`. 클릭 후 `i8cJw` 라벨 출현을 `wait_for_function` 으로 명시 대기 (500ms).
- **그룹 라벨 펼침** (`DAY_GROUP_EXPANSION`): `매일` → 월~일, `평일` → 월~금, `주말` → 토일.
- **다중 라인 시간 블록** (`_parse_time_block`): 한 H3ua4 안에 `<br>` 으로 묶인 영업시간 / 브레이크타임 / 라스트오더 라인 분해.
- **시간 정규식** (`_RE_TIME_RANGE`): `HH:MM - HH:MM`, 사이에 `다음 날` 옵셔널 토큰 허용 (예: `14:00 - 다음 날 02:00`).

### db.py
- `details.db` 스키마 정의 (`SCHEMA`) + 기존 DB 마이그레이션 (`ADD_COLUMNS`).
- `init_db()` 호출 시 `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` 자동 적용.

#### 스키마

```sql
CREATE TABLE stores (
    store_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    mgtno           TEXT UNIQUE,              -- 인허가 관리번호 (1 source ↔ 1 store)
    name            TEXT NOT NULL,            -- 인허가 BPLCNM
    address         TEXT,                     -- 인허가 RDNWHLADDR
    naver_place_id  TEXT                      -- 네이버 매칭 결과 (NULL 가능)
);
CREATE INDEX idx_stores_place ON stores(naver_place_id);

CREATE TABLE menus (
    store_id   INTEGER NOT NULL,
    menu_name  TEXT NOT NULL,
    price      TEXT,                          -- 가공 전 raw (예: "8,000원")
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);
CREATE INDEX idx_menus_store ON menus(store_id);

CREATE TABLE business_hours (
    store_id     INTEGER NOT NULL,
    day_of_week  TEXT NOT NULL,               -- '월'~'일'
    open_time    TEXT,                        -- 'HH:MM'
    close_time   TEXT,
    is_closed    INTEGER NOT NULL DEFAULT 0,  -- 0/1
    break_start  TEXT,                        -- 브레이크 시작 (NULL 가능)
    break_end    TEXT,
    last_order   TEXT,                        -- 라스트오더 (NULL 가능)
    PRIMARY KEY (store_id, day_of_week),
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
);
```

### coord.py
- `tm_to_wgs84(x, y)` — `pyproj` 로 EPSG:5174 → EPSG:4326 변환. 실측 2m 오차로 검증.
- `parse_tm(x_raw, y_raw)` — 문자열 형태의 TM 좌표 → `(lng, lat)` 또는 `None`.
- `haversine_m(lng1, lat1, lng2, lat2)` — 두 WGS84 좌표 사이 거리 (미터).

### run.py
- 진입점. 주요 함수:
  - `load_source_stores(limit)` — `restaurants` 테이블에서 `(MGTNO, BPLCNM, 주소, X, Y)` 로드.
  - `get_existing_place_id(conn, mgtno)` — 이미 매칭된 pid 가 있으면 검색 단계 스킵.
  - `upsert_store(conn, mgtno, name, address, place_id)` — `mgtno` UNIQUE 기준 upsert. place_id 가 바뀌면 UPDATE.
  - `replace_menus`, `replace_hours` — 기존 행 DELETE 후 새로 INSERT (멱등).
- 실행 흐름: 연속 실패 `MAX_FAIL=20` 건 시 차단 의심 중단. 가게 단위 `THROTTLE=1.5초` 대기.
- 디버그 출력: 첫 번째 가게에 대해서만 `verbose=True` (응답 덤프, DOM 구조 확인용).

## 매칭 로직 핵심 의사결정

| 결정 | 이유 |
|---|---|
| 좌표 기반 1차 필터 (300m) | 동명이업소·분점 구분에 가장 강력. 텍스트보다 정확. |
| 좌표 미보유 시 도로명 베이스 필터 | 인허가 X/Y 미보유율 ~55%. 도로명(`삼선교로` vs `동소문로`) 으로 같은 구/동 내 분리. |
| 이름 미일치 시 매칭 폐기 | 폴백 `candidates[0]` 반환이 명백한 오매칭 (예: 옛날불고기↔푸른농장) 을 만든 원인. `None` 반환이 안전. |
| `mgtno` UNIQUE | 한 인허가 → 한 store 보장. 재실행 시 새 매칭으로 자동 UPDATE. |
| `naver_place_id` 는 비 UNIQUE | 동명 다른 가게가 같은 네이버 페이지로 묶이는 정당한 케이스 허용. |

## 실행

```powershell
# 사전 준비
cd Backend
pip install -r requirements.txt
playwright install chromium

# 전체 크롤
python -m src.crawler.run

# 처음 N건만 테스트
python -m src.crawler.run 10

# 브라우저 창 띄워서 디버깅
$env:HEADLESS=0
python -m src.crawler.run

# 단일 가게 매칭/디테일 테스트
python -m src.crawler.search "동궁찜닭"
python -m src.crawler.detail 1230199721
```

## 환경변수

| 이름 | 기본 | 효과 |
|---|---|---|
| `HEADLESS` | `1` | `0` 시 브라우저 창 표시 |
| `SLOW_MO` | `0` | Playwright 액션 사이 N ms 대기 |
| `DEBUG` | (unset) | 모든 가게에 대해 verbose 디버그 출력 |

## 운영 가이드

- **재크롤 안전성**: `mgtno` UNIQUE + `replace_menus`/`replace_hours` 가 멱등 — 같은 명령 반복 실행 시 부작용 없음.
- **부분 재크롤**: `get_existing_place_id` 가 검색 단계만 스킵, 메뉴/영업시간은 매번 갱신.
- **미매칭 한정 재실행**: 인라인 스크립트로 `stores` 의 NULL pid 만 필터링 (사용 예시는 운영 노트 참조).
- **디버그 덤프**: `src/crawler/_debug/` — 검색 응답 JSON, 페이지 HTML, Apollo state 등. `.gitignore` 처리됨.
- **차단 회피**: `THROTTLE=1.5s` + 연속 실패 20건 시 자동 중단. 차단 시 IP 변경 또는 일정 시간 대기 후 재실행.
