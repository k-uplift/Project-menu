/**
 * 데이터 타입 정의 (JSDoc)
 *
 * - JS 환경에서도 IDE 자동완성과 타입 힌트가 동작하도록 JSDoc로 정의
 * - 실제 LLM / CF / DB와 연결될 때 이 스키마를 그대로 사용하면 됨
 *
 * (TypeScript로 옮기고 싶다면 이 파일을 그대로 .ts로 바꾸고 export 하면 됨)
 */

/**
 * @typedef {Object} Keyword
 * @property {string} id              - 키워드 고유 ID (예: 'kw-warm')
 * @property {string} label           - 화면에 표시할 텍스트 (예: '따뜻한')
 * @property {number} [confidence]    - LLM이 평가한 신뢰도 (0~1) — 추후 표시용
 * @property {'llm'|'user'} source    - 키워드 출처 (LLM 추출 vs 사용자 추가)
 */

/**
 * LLM 분석 결과
 * @typedef {Object} AnalyzeResult
 * @property {string} originalText    - 사용자가 입력한 원문
 * @property {Keyword[]} keywords     - 추출된 키워드 목록
 * @property {string} [intent]        - 한 줄로 요약한 의도 (선택)
 */

/**
 * 추천 이유 (RecommendScreen 카드에 그대로 표시)
 *
 * 교수님 피드백 반영:
 *  - 감성 키워드 매칭
 *  - 유사 사용자 선택 (CF)
 *  - 상황 기반 (날씨/시간 등)
 * 세 종류를 명시적으로 분리해 추천 근거를 투명하게 노출
 *
 * @typedef {Object} RecommendReason
 * @property {string[]} matchedKeywords   - 매칭된 감성 키워드
 * @property {number} cfScore             - 협업 필터링 점수 (0~1)
 * @property {string} cfDescription       - 예: "비슷한 취향 유저 87%가 선택"
 * @property {string} contextNote         - 예: "비 오는 저녁에 자주 선택됨"
 */

/**
 * 음식 추천 카드
 * @typedef {Object} FoodItem
 * @property {string} id
 * @property {string} name             - 음식 이름
 * @property {string} emoji            - 표시용 이모지
 * @property {string[]} tags           - 음식이 가진 키워드(태그)
 * @property {number} score            - 종합 추천 점수 (0~100)
 * @property {RecommendReason} reason  - 추천 이유 객체
 */

/**
 * 음식점
 * @typedef {Object} Restaurant
 * @property {string} id
 * @property {string} name
 * @property {number} rating           - 0~5
 * @property {number} reviewCount
 * @property {number} distanceKm       - km 단위
 * @property {number} walkMin          - 도보 분
 * @property {string} priceRange       - 예: "8,000~15,000원"
 * @property {boolean} delivery        - 배달 가능 여부
 * @property {string} address
 * @property {string} category         - 카테고리 (예: "한식 · 찌개")
 * @property {number} cfMatch          - CF 기반 취향 일치도 (0~1)
 */

// 빈 export — JSDoc 타입은 import 없이도 IDE가 인식
export {};
