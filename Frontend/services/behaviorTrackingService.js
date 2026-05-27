/**
 * behaviorTrackingService.js
 *
 * 사용자 행동을 서버로 전송하는 서비스 (CF 추천 학습용)
 *
 * 점수 정책:
 *  - food_card_click    : 1점  (음식 카드 클릭)
 *  - navigate_click     : 2점  (음식점 상세에서 길찾기 클릭)
 *  - delivery_click     : 2점  (음식점 상세에서 배달의민족 클릭)
 *
 * 현재: mock (콘솔 출력)
 * 추후: POST /api/events 로 서버 전송 — 함수 시그니처 그대로 유지
 *
 * 설계 원칙:
 *  - "fire-and-forget" — UI를 막지 않도록 await 없이 호출 가능
 *  - 네트워크 실패 시 큐에 쌓아두고 재시도 (현재는 mock이라 그냥 콘솔)
 *  - 행동 종류별 점수는 서버에서 검증 — 프론트에서 임의 조작 불가하게
 */

// 행동 타입별 점수 (참고용 — 실제 점수는 서버에서 매핑/검증)
export const BEHAVIOR_SCORES = {
  food_card_click: 1,
  navigate_click: 2,
  delivery_click: 2,
};

// 서버 엔드포인트 (추후 실제 URL로 교체)
const EVENT_ENDPOINT = 'https://api.menu-app.com/events';

/**
 * 행동 이벤트 전송 (메인 함수)
 *
 * @param {string} eventType     - 'food_card_click' | 'navigate_click' | 'delivery_click'
 * @param {Object} payload       - 추가 데이터 (음식 ID, 음식점 ID 등)
 * @returns {Promise<void>}      - 항상 resolve (실패해도 throw 안 함)
 */
export async function trackBehavior(eventType, payload = {}) {
  const event = {
    type: eventType,
    score: BEHAVIOR_SCORES[eventType] || 0,
    payload,
    timestamp: Date.now(),
    // 추후 사용자 식별자 추가:
    // userId: await getCurrentUserId(),
    // sessionId: getCurrentSessionId(),
  };

  // === [실제 서버 연결 시 이 부분 교체] ===
  //
  // try {
  //   await fetch(EVENT_ENDPOINT, {
  //     method: 'POST',
  //     headers: { 'Content-Type': 'application/json' },
  //     body: JSON.stringify(event),
  //   });
  // } catch (e) {
  //   // 실패 시 큐에 저장하고 다음 기회에 재전송
  //   await queueFailedEvent(event);
  // }
  //
  // ========================================

  // 현재는 mock: 콘솔에 출력 (개발/시연 확인용)
  console.log(
    `[BehaviorTracking] ${eventType} (+${event.score}점)`,
    payload
  );

  // 서버 응답 시뮬레이션 (실제 fetch 흉내)
  return Promise.resolve({ ok: true, event });
}

// =====================================================
// 각 행동별 헬퍼 함수 — 호출하는 쪽 코드를 깔끔하게
// =====================================================

/**
 * 음식 카드 클릭 (+1점)
 * @param {Object} food - { id, name, tags }
 */
export function trackFoodCardClick(food) {
  return trackBehavior('food_card_click', {
    foodId: food?.id,
    foodName: food?.name,
    tags: food?.tags,
  });
}

/**
 * 길찾기 버튼 클릭 (+2점)
 * @param {Object} restaurant
 * @param {Object} food - 어떤 음식 → 어떤 음식점 흐름인지 추적
 */
export function trackNavigateClick(restaurant, food) {
  return trackBehavior('navigate_click', {
    restaurantId: restaurant?.id,
    restaurantName: restaurant?.name,
    foodId: food?.id,
    foodName: food?.name,
  });
}

/**
 * 배달의민족 버튼 클릭 (+2점)
 * @param {Object} restaurant
 * @param {Object} food
 */
export function trackDeliveryClick(restaurant, food) {
  return trackBehavior('delivery_click', {
    restaurantId: restaurant?.id,
    restaurantName: restaurant?.name,
    foodId: food?.id,
    foodName: food?.name,
  });
}
