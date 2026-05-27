# Data Pipeline 명세

`Backend/src/data/` 의 인허가 데이터 수집·정제 모듈 명세. 서울 열린데이터광장 API 로부터 일반음식점 인허가 정보를 받아 정제된 가게 목록을 만든다.

## 입력 / 출력

| 구분 | 위치 | 내용 |
|---|---|---|
| 입력 | `openapi.seoul.go.kr` API (`LOCALDATA_072404` 서비스) | 서울시 일반음식점 인허가 정보 전체 |
| 중간 | `Backend/db/raw.db` / `raw_restaurants` 테이블 | 전체 raw 데이터 (대용량, gitignore) |
| 출력 | `Backend/db/restaurants.db` / `restaurants` 테이블 | 성북구 8개 동 + 영업중 필터링 결과 |

## 모듈 구조

```
src/data/
  fetch.py   API 호출 + raw.db 적재 + clean.py 자동 호출
  clean.py   raw.db → restaurants.db 정제
```

## 데이터 흐름

```
서울 열린데이터광장 API
  http://openapi.seoul.go.kr:8088/{KEY}/json/LOCALDATA_072404/{start}/{end}/
    │
    │  fetch.py  ──  1,000건씩 페이지네이션, 재시도 3회
    ▼
raw.db / raw_restaurants  (38개 컬럼, PK = MGTNO)
    │
    │  clean.py  ──  성북구(OPNSFTEAMCODE=3070000) + 영업중(TRDSTATEGBN=01)
    │               + 지정 동 8곳 (LIKE 매칭)
    ▼
restaurants.db / restaurants
```

## 모듈별 책임

### fetch.py
- 서울 열린데이터광장 OpenAPI `LOCALDATA_072404` (일반음식점 인허가 정보) 전수 수집.
- 인증: `.env` 의 `KEY` 환경변수.
- 페이지네이션: `BATCH_SIZE=1000` 건씩, 1~total 까지 반복.
- 재시도: 실패 시 `MAX_RETRY=3` 회 (각 시도 사이 `RETRY_DELAY=5초`).
- 호출 사이 `THROTTLE=0.1초`.
- 멱등: `INSERT OR REPLACE` + PK=`MGTNO` 라 중복 호출해도 데이터 일관됨.
- 완료 후 `run_clean()` 자동 호출 → `restaurants.db` 갱신.

#### 수집 컬럼 (38개)

| 카테고리 | 컬럼 |
|---|---|
| 식별 | `OPNSFTEAMCODE` (인허가기관), `MGTNO` (관리번호, PK), `APVPERMYMD` (인허가일자) |
| 영업 상태 | `TRDSTATEGBN`, `TRDSTATENM`, `DTLSTATEGBN`, `DTLSTATENM`, `DCBYMD` (폐업일자) |
| 주소·연락처 | `SITETEL`, `SITEAREA`, `SITEPOSTNO`, `SITEWHLADDR` (지번), `RDNWHLADDR` (도로명), `RDNPOSTNO` |
| 가게 | `BPLCNM` (상호), `LASTMODTS`, `UPDATEGBN`, `UPDATEDT`, `UPTAENM` (업태) |
| 좌표 | `X` (TM 경도), `Y` (TM 위도) — EPSG:5174 |
| 종업원·시설 | `SNTUPTAENM`, `MANEIPCNT`, `WMEIPCNT`, `TRDPJUBNSENM`, `LVSENM`, `WTRSPLYFACILSENM`, `HOFFEPCNT`, `FCTYOWKEPCNT`, `FCTYSILJOBEPCNT`, `FCTYPDTJOBEPCNT`, `BDNGOWNSENM`, `ISREAM`, `MONAM`, `MULTUSNUPSOYN`, `FACILTOTSCP` |
| 식품접객업 | `JTUPSOASGNNO`, `JTUPSOMAINEDF`, `HOMEPAGE` |

### clean.py
- `raw_restaurants` 의 전체 데이터를 필터링해 `restaurants` 테이블 생성.
- `DROP TABLE IF EXISTS` 후 `CREATE TABLE AS SELECT` — 매 실행마다 통째로 재생성.
- `ATTACH DATABASE` 로 `raw.db` 를 `restaurants.db` 트랜잭션에 연결해 1회 쿼리로 처리.

#### 필터 조건

```sql
WHERE OPNSFTEAMCODE = '3070000'    -- 성북구
  AND TRDSTATEGBN  = '01'          -- 영업중 / 정상
  AND (SITEWHLADDR LIKE '%삼선동1가%'
    OR SITEWHLADDR LIKE '%삼선동2가%'
    OR SITEWHLADDR LIKE '%삼선동3가%'
    OR SITEWHLADDR LIKE '%삼선동4가%'
    OR SITEWHLADDR LIKE '%삼선동5가%'
    OR SITEWHLADDR LIKE '%동소문동2가%'
    OR SITEWHLADDR LIKE '%동소문동3가%'
    OR SITEWHLADDR LIKE '%동소문동5가%')
```

대상 동 8곳은 한성대 / 성신여대 주변 시연 범위. 변경 시 `clean.py:TARGET_DONGS` 수정.

## 주요 의사결정

| 결정 | 이유 |
|---|---|
| `MGTNO` 를 PK | 인허가별 고유키. 같은 가게가 폐업·재등록되면 MGTNO 가 달라 별개 row 가 됨. |
| `INSERT OR REPLACE` | API 가 같은 MGTNO 의 데이터를 갱신하는 경우 (최신 상태 유지) 대응. |
| raw.db 와 restaurants.db 분리 | raw 는 대용량 (전 서울), 정제본만 git/배포에 포함. raw.db 는 `.gitignore`. |
| 도로명 우선, 지번 폴백 | 인허가 일부 행은 도로명 주소가 비어있음. `COALESCE(NULLIF(TRIM(RDNWHLADDR), ''), SITEWHLADDR)` 패턴은 crawler 의 `load_source_stores` 에서도 동일하게 사용. |
| TM 좌표계 보관 | API 가 EPSG:5174 로 제공. crawler 의 `coord.py` 에서 WGS84 변환. |

## 실행

```powershell
cd Backend
pip install -r requirements.txt

# .env 에 API 키 설정
echo "KEY=발급받은_API_키" > .env

# 전체 수집 + 정제
python -m src.data.fetch

# 정제만 다시 실행 (raw.db 가 이미 있을 때)
python -m src.data.clean
```

## 환경변수

| 이름 | 기본 | 효과 |
|---|---|---|
| `KEY` | (필수) | 서울 열린데이터광장 API 키. `.env` 또는 셸 환경에 설정. |

## 운영 가이드

- **재수집 안전성**: `INSERT OR REPLACE` 라 중복 실행 시 데이터 일관성 유지. 단 raw.db 의 디스크 점유는 늘어남 → 필요 시 직접 삭제.
- **부분 갱신 불가**: 현재는 전수 수집만. 증분 갱신은 미구현 (`UPDATEDT` 활용 가능).
- **다른 자치구 / 동으로 확장**: `clean.py` 의 `OPEN_TEAM_CODE` (구) 와 `TARGET_DONGS` (동 리스트) 만 수정하면 됨. `OPNSFTEAMCODE` 매핑은 행정자치부 표준 코드 참조.
- **데이터 한계**: 인허가 정보일 뿐 실제 영업 여부는 확인 불가 — 폐업했지만 인허가는 살아있는 케이스 존재. `TRDSTATENM` / `DCBYMD` 로 어느 정도 필터링되지만 100% 는 아님. 네이버 크롤링 단계에서 매칭 실패로 자연 도태됨.
- **API 응답 코드**: `INFO-000` 정상, `INFO-200` 결과 0건 (정상), 그 외는 에러로 처리.

## 현재 데이터 규모

- 서울 전체 일반음식점 (raw): 약 십수만 건
- 정제 후 (성북구 8동, 영업중): **402건**

## 다음 단계 후보

- **X/Y 미보유 row 보강** — 카카오/네이버 geocoding API 로 주소 → 좌표 변환 (현재 약 55% 가 좌표 없음).
- **증분 갱신** — `UPDATEDT` 기반 새/변경된 행만 가져오기.
- **다른 업종 추가** — 휴게음식점 (`LOCALDATA_072405`) 등을 별도 테이블로 통합.
