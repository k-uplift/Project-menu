# [임시 메모] 음식-태그 매핑 동적 학습 방안

> 본 명세는 확정 전 검토용 메모입니다. 현재 `SPEC.md`의 `FoodTag`는 정적 시드 매핑으로 유지하고, 아래 내용은 추후 도입 여부를 결정합니다.

## 목적

음식별 누적 행동 데이터를 바탕으로 **시간 감쇠**를 적용해 **Top-K 태그**를 주기적으로 재선정하여 `FoodTag`를 동적으로 갱신.

## 신규/변경 테이블

### (변경) FoodTag — 출처 컬럼 추가

| 컬럼명 | 타입 | 제약 | 설명 |
|---|---|---|---|
| food_id | INT | PK, FK (Food) | 음식 ID |
| tag_id | INT | PK, FK (Tag) | 태그 ID |
| source | ENUM('seed', 'learned') | NOT NULL DEFAULT 'seed' | 매핑 출처 |
| updated_at | TIMESTAMP | ON UPDATE CURRENT_TIMESTAMP | 마지막 갱신 |

- **seed**: 운영자 정의. 자동 삭제 X.
- **learned**: 배치가 생성·갱신. 매 배치마다 재계산.

### (신규) FoodTagWeight — 음식-태그 가중치 집계

| 컬럼명 | 타입 | 제약 | 설명 |
|---|---|---|---|
| food_id | INT | PK, FK (Food) | 음식 ID |
| tag_id | INT | PK, FK (Tag) | 태그 ID |
| decayed_weight | DECIMAL(10,4) | DEFAULT 0 | 시간 감쇠 적용된 누적 가중치 |
| updated_at | TIMESTAMP | ON UPDATE CURRENT_TIMESTAMP | 마지막 갱신 |

## 시간 감쇠 방식 (옵션)

| 방식 | 동작 | 비고 |
|---|---|---|
| A. 배치 곱셈 감쇠 | 매일 `decayed_weight *= 0.951` | 단순. **초기 권장** |
| B. 원천 로그 재계산 | 배치 시 `exp(-λ × Δt)` 가중치로 재집계 | 정확. 비용 ↑ |
| C. 하이브리드 | 일상은 A, 주 1회 B 보정 | 균형 |

- 기본 제안: 반감기 14일 → `daily_decay = 0.5^(1/14) ≈ 0.951`

## 갱신 흐름

```
[실시간]
유저 행동 발생
  ├→ UserInteractionLog INSERT
  ├→ UserFoodTagWeight  UPSERT
  └→ FoodTagWeight      UPSERT (raw weight 누적)

[일일 배치]
FoodTagWeight.decayed_weight *= 0.951

[주간 배치] Top-K 재선정
DELETE FROM FoodTag WHERE source = 'learned';
INSERT INTO FoodTag (food_id, tag_id, source)
SELECT food_id, tag_id, 'learned'
FROM (
  SELECT food_id, tag_id,
    ROW_NUMBER() OVER (PARTITION BY food_id ORDER BY decayed_weight DESC) AS rk
  FROM FoodTagWeight
  WHERE decayed_weight >= [최소 임계치]
) ranked
WHERE rk <= K;
```

## 파라미터 (잠정안)

| 파라미터 | 잠정값 | 비고 |
|---|---|---|
| K (Top-K) | 5 | 음식당 학습 태그 최대 개수 |
| 반감기 | 14일 | 일일 감쇠 0.951 |
| 최소 임계치 | TBD | 너무 적은 행동은 학습 제외 |
| Top-K 재선정 주기 | 주 1회 | 배치 비용 vs 반영 지연 |

## 위험 요소 / 완화책

| 위험 | 설명 | 완화책 |
|---|---|---|
| 자기강화 루프 | 학습 태그가 추천 → 같은 태그 강화 → 다양성 손실 | 시드 보존, exploration 비율, 강한 감쇠 |
| Cold start | 신규 음식은 행동 없어 learned 태그 0 | seed 태그가 필수 베이스라인 |
| 노이즈 학습 | 잘못된 의도로 선택된 시그널이 학습됨 | 시드 충돌 시 페널티, 최소 행동 수 임계치 |

## 결정 보류 항목

- 도입 시점 (MVP 이후?)
- K, 반감기, 최소 임계치 수치 확정
- 시드 ↔ 학습 충돌 처리 정책
- exploration 비율 도입 여부
