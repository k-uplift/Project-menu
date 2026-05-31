/**
 * behaviorTrackingService.js
 *
 * 사용자 행동 신호 수집 (마이페이지 칭호 + CF 학습용)
 *
 * 점수 정책 (CF 신호 단일화 — implicit-only, 5/29 결정):
 *  - food_card_click    : 1점  (음식 카드 클릭, 관심)
 *  - navigate_click     : 2점  (길찾기, 최종 선택)
 *  - delivery_click     : 2점  (배달의민족, 최종 선택)
 *
 * 저장:
 *  - AsyncStorage 누적 (max 500개) — 마이페이지 칭ho의 데이터 source
 *  - 서버 POST /events (fire-and-forget) — recommend.db의
 *    UserInteractionLog + UserFoodTagWeight 갱신용. 양혜원 개인화 CF의 입력.
 *
 * 설계 원칙:
 *  - "fire-and-forget" — UI를 막지 않도록 await 없이 호출 가능
 *  - 저장 실패해도 throw 안 함 (콘솔만)
 *  - 로컬·서버 둘 다 시도. 서버 실패해도 로컬 누적은 정상 작동.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_BASE } from '../constants/api';

export const BEHAVIOR_SCORES = {
  food_card_click: 1,
  navigate_click: 2,
  delivery_click: 2,
};

// 서버 측 ENUM과 매핑 — schema.UserInteractionLog.action_type
const SERVER_ACTION_TYPE = {
  food_card_click: 'click',
  navigate_click: 'final_select',
  delivery_click: 'final_select',
};

const EVENTS_KEY = '@menu/behavior_events';
// 칭호 부여에 충분한 누적량 + AsyncStorage 부담 적게. 평균 한 이벤트 ~200B
// 가정 시 500개 = 100KB. 마이페이지 통계엔 차고 넘침.
const MAX_EVENTS = 500;

async function readJSON(key, fallback = []) {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    console.warn(`[behaviorTracking] read ${key} failed:`, e);
    return fallback;
  }
}

async function writeJSON(key, value) {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.warn(`[behaviorTracking] write ${key} failed:`, e);
  }
}

/**
 * 행동 이벤트 기록 (메인 함수). 로컬 AsyncStorage + 서버 POST 동시.
 *
 * @param {string} eventType  - 'food_card_click' | 'navigate_click' | 'delivery_click'
 * @param {Object} payload    - 추가 데이터 (음식·식당·태그·카테고리 등)
 * @param {Object} ctx        - { sessionId?:number, userId?:number=1 } — 서버 UPSERT용
 * @returns {Promise<{ok:boolean, event:Object}>}
 */
export async function trackBehavior(eventType, payload = {}, ctx = {}) {
  const event = {
    type: eventType,
    score: BEHAVIOR_SCORES[eventType] || 0,
    payload,
    timestamp: Date.now(),
  };

  // (1) 로컬 — 마이페이지 칭호 source. 새 이벤트가 맨 앞. max 초과 시 오래된 것 폐기.
  const list = await readJSON(EVENTS_KEY, []);
  await writeJSON(EVENTS_KEY, [event, ...list].slice(0, MAX_EVENTS));

  console.log(
    `[BehaviorTracking] ${eventType} (+${event.score}점)`,
    payload
  );

  // (2) 서버 POST — recommend.db UserInteractionLog + UserFoodTagWeight 갱신.
  //     fire-and-forget. 실패해도 로컬 누적은 정상.
  const actionType = SERVER_ACTION_TYPE[eventType];
  const foodName = payload?.foodName;
  if (actionType && foodName) {
    fetch(`${API_BASE}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: ctx.userId ?? 1,
        session_id: ctx.sessionId ?? null,
        food_name: foodName,
        action_type: actionType,
      }),
    })
      .then((r) => {
        if (!r.ok) console.warn(`[behaviorTracking] POST /events HTTP ${r.status}`);
      })
      .catch((e) => console.warn('[behaviorTracking] POST /events 실패:', e.message));
  }

  return { ok: true, event };
}

/**
 * 누적된 모든 이벤트 가져오기 (최신 순)
 * 마이페이지 칭호 부여 로직(badges.js)이 이걸 받아 stats 계산.
 */
export async function getBehaviorEvents() {
  return readJSON(EVENTS_KEY, []);
}

/**
 * 누적 이벤트 전체 삭제 (디버그/마이페이지 초기화용)
 */
export async function clearBehaviorEvents() {
  await AsyncStorage.removeItem(EVENTS_KEY);
}

// =====================================================
// 각 행동별 헬퍼 — 호출하는 쪽 코드를 깔끔하게 + 칭호용 payload 보강
// =====================================================

/**
 * 음식 카드 클릭 (+1점, 관심)
 *
 * @param {Object} food - { id, name, tags, ... }
 * @param {Object} [ctx] - { sessionId, userId } — 서버 UPSERT 묶음용
 */
export function trackFoodCardClick(food, ctx = {}) {
  return trackBehavior('food_card_click', {
    foodId: food?.id,
    foodName: food?.name,             // 칭호 C용 (kind 이름 그대로)
    foodTags: food?.tags,             // 칭호 A용 (시드 14개)
  }, ctx);
}

/**
 * 길찾기 버튼 클릭 (+2점, 최종 선택)
 *
 * @param {Object} restaurant - { id, name, category, ... }
 * @param {Object} food
 * @param {Object} [ctx] - { sessionId, userId }
 */
export function trackNavigateClick(restaurant, food, ctx = {}) {
  return trackBehavior('navigate_click', {
    restaurantId: restaurant?.id,
    restaurantName: restaurant?.name,
    restaurantCategory: restaurant?.category,  // 칭호 B용 (한식/일식 등)
    foodId: food?.id,
    foodName: food?.name,                      // 칭호 C용
    foodTags: food?.tags,                      // 칭호 A용
  }, ctx);
}

/**
 * 배달의민족 버튼 클릭 (+2점, 최종 선택)
 *
 * @param {Object} restaurant - { id, name, category, ... }
 * @param {Object} food
 * @param {Object} [ctx] - { sessionId, userId }
 */
export function trackDeliveryClick(restaurant, food, ctx = {}) {
  return trackBehavior('delivery_click', {
    restaurantId: restaurant?.id,
    restaurantName: restaurant?.name,
    restaurantCategory: restaurant?.category,
    foodId: food?.id,
    foodName: food?.name,
    foodTags: food?.tags,
  }, ctx);
}
