/**
 * recommendationService.js
 *
 * 키워드(+컨텍스트) → 음식 추천
 *
 * 백엔드(FastAPI /foods) 호출:
 *  - 자연어 쿼리는 originalText 우선, 없으면 키워드 라벨 join
 *  - 응답의 kinds[]가 프론트의 FoodItem 계약과 일치 (백엔드 to_kind_group()가 맞춰줌)
 *  - 시간·날씨 기반 contextNote는 클라이언트 사이드에서 보강
 *
 * CF 백엔드는 미구현 — getPersonalizedRecommendations는 임시로 base와 동일.
 * CF 엔드포인트 붙으면 별도 fetch로 분리 예정.
 */

import { API_BASE } from '../constants/api';
import {
  getCurrentTimeContext,
  getCurrentWeather,
  getCombinedContextReason,
} from './contextService';
import { getCurrentUser } from './authService';


/** 현재 로그인 사용자의 user_id. 비로그인이면 1 (시연용 Alice = T1 매운국물파). */
async function getDefaultUserId() {
  try {
    const user = await getCurrentUser();
    return user?.user_id ?? 1;
  } catch {
    return 1;
  }
}

/**
 * @typedef {Object} RecommendContext
 * @property {string}   [originalText]                - 사용자가 입력한 자연어 원문 (가장 정확)
 * @property {Object}   [timeCtx]                     - getCurrentTimeContext() 결과
 * @property {Object}   [weatherCtx]                  - getCurrentWeather() 결과
 * @property {{weather:number, time:number, taste:number}} [weights]
 * @property {{soup:'yes'|'no'|'any', people:'solo'|'2'|'3+', calorie:'low'|'mid'|'high'}} [conditions]
 * @property {number}   [refreshSeed]                 - 클라이언트 새로고침용(백엔드는 무시)
 */

/**
 * 음식 추천 받기. sessionId·userId를 응답에 포함해 후속 이벤트 트래킹과 묶을 수 있게 함.
 *
 * @param {import('../types').Keyword[]} keywords
 * @param {RecommendContext} [context]
 * @returns {Promise<{ items: import('../types').FoodItem[], sessionId: number|null, userId: number }>}
 */
export async function getFoodRecommendations(keywords, context = {}) {
  const defaultUid = await getDefaultUserId();
  if (!keywords || keywords.length === 0) {
    return { items: [], sessionId: null, userId: context.userId ?? defaultUid };
  }

  // 사용자가 KeywordScreen 에서 *직접 확인·수정*한 시드 태그를 그대로 백엔드에
  // 전달. /foods 의 tags 파라미터 모드 — extract 건너뛰고 *주어진 태그*로 매칭.
  // 사용자 변경(추가/제거)이 100% 추천에 반영. originalText 는 추적용으로만 유지.
  // food_keywords 는 /extract 가 추출한 *카테고리·식재료* 신호를 같이 흘려보냄
  // → tags 모드에서도 match.py 의 substring 매칭이 살아남 (Claude 추가 호출 없음).
  const tagList = keywords.map((k) => k.label).join(',');
  const fkwList = (context.foodKeywords || []).join(',');

  let kinds = [];
  let sessionId = null;
  let userId = context.userId ?? defaultUid;
  try {
    const fkwParam = fkwList ? `&food_keywords=${encodeURIComponent(fkwList)}` : '';
    const url = `${API_BASE}/foods?tags=${encodeURIComponent(tagList)}${fkwParam}&user_id=${userId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    kinds = Array.isArray(data.kinds) ? data.kinds : [];
    sessionId = data.sessionId ?? null;
    userId = data.userId ?? userId;
  } catch (e) {
    console.warn('[recommendationService] /foods fetch 실패:', e.message);
    return { items: [], sessionId: null, userId };
  }

  // 동적 contextNote(시간·날씨) — 백엔드 응답에는 항상 null이라 클라가 채움
  const timeCtx = context.timeCtx || getCurrentTimeContext();
  const weatherCtx = context.weatherCtx || (await getCurrentWeather());
  const dynamicContextNote = getCombinedContextReason(timeCtx, weatherCtx);

  const items = kinds.map((food) => ({
    ...food,
    reason: {
      ...food.reason,
      contextNote: dynamicContextNote,
    },
  }));
  return { items, sessionId, userId };
}

/**
 * "나를 위한 추천" — CF 기반 정렬 (cf_module, 양혜원)
 *
 * 백엔드 /foods_cf 호출. user_id 기본 1 (시연용 합성 페르소나).
 * 응답 모양은 /foods와 동일 — 카드 컴포넌트 그대로 사용.
 *
 * 실 사용자 도입 시 user_id 인자로 받도록 확장. 일단 시연에선 익명 → user_id=1.
 */
export async function getPersonalizedRecommendations(keywords, context = {}) {
  const defaultUid = await getDefaultUserId();
  if (!keywords || keywords.length === 0) {
    return { items: [], sessionId: null, userId: context.userId ?? defaultUid };
  }

  // /foods 와 동일 패턴 — 사용자 선택 시드를 tags 파라미터로 직접 전달.
  // food_keywords 는 cf_module Tab2 점수엔 안 쓰지만 *세션 메타데이터* 보존용으로 같이 보냄.
  const tagList = keywords.map((k) => k.label).join(',');
  const fkwList = (context.foodKeywords || []).join(',');

  let kinds = [];
  let sessionId = null;
  let userId = context.userId ?? defaultUid;
  let emptyReason = null;
  try {
    const fkwParam = fkwList ? `&food_keywords=${encodeURIComponent(fkwList)}` : '';
    const url = `${API_BASE}/foods_cf?tags=${encodeURIComponent(tagList)}${fkwParam}&user_id=${userId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    kinds = Array.isArray(data.kinds) ? data.kinds : [];
    sessionId = data.sessionId ?? null;
    userId = data.userId ?? userId;
    emptyReason = data.emptyReason ?? null;
  } catch (e) {
    console.warn('[recommendationService] /foods_cf fetch 실패:', e.message);
    return { items: [], sessionId: null, userId };
  }

  // Cold start — 아직 행동 이력이 없는(신규 가입) 사용자는 CF가 닮은 사용자를
  // 못 찾아 빈 결과(emptyReason='no_history')를 준다. 빈 화면 대신 기본 추천으로
  // 대체하고 fallback 플래그를 띄워 '취향 학습 전' 배너를 보여준다.
  if (kinds.length === 0) {
    const base = await getFoodRecommendations(keywords, context);
    return { ...base, fallback: true, fallbackReason: emptyReason || 'no_history' };
  }

  const timeCtx = context.timeCtx || getCurrentTimeContext();
  const weatherCtx = context.weatherCtx || (await getCurrentWeather());
  const dynamicContextNote = getCombinedContextReason(timeCtx, weatherCtx);

  const items = kinds.map((food) => ({
    ...food,
    reason: {
      ...food.reason,
      contextNote: dynamicContextNote,
    },
  }));
  return { items, sessionId, userId, fallback: false };
}

/**
 * 나와 취향이 닮은 사용자 — user-based CF 유사도 상위 K명.
 *
 * 백엔드 /similar_users 호출. 각 item: {userId, name, match(0~100), sharedFoods[]}.
 * cold start(행동 이력 없는 신규 사용자)면 빈 배열 — 호출처가 섹션 숨김 처리.
 */
export async function getSimilarUsers(userId = 1, topK = 5) {
  try {
    const res = await fetch(`${API_BASE}/similar_users?user_id=${userId}&top_k=${topK}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return Array.isArray(data.users) ? data.users : [];
  } catch (e) {
    console.warn('[recommendationService] /similar_users 실패:', e.message);
    return [];
  }
}

/**
 * 마이페이지 칭호·미식유형을 *서버 user_id 기준*으로 계산하기 위한 행동 데이터.
 *
 * 백엔드 /user_events 호출 — recommend.db의 그 user_id 행동 이력을
 * behaviorTrackingService 이벤트 모양으로 복원해 돌려준다.
 * 반환: { events:[{type,timestamp,payload:{foodName,foodTags,restaurantCategory}}],
 *        searches:[{timestamp}], preferredTags:[{tag,count}] }.
 * 실패 시 null — 호출처가 로컬 AsyncStorage로 폴백.
 */
export async function getUserEvents(userId = 1) {
  try {
    const res = await fetch(`${API_BASE}/user_events?user_id=${userId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return {
      events: Array.isArray(data.events) ? data.events : [],
      searches: Array.isArray(data.searches) ? data.searches : [],
      preferredTags: Array.isArray(data.preferredTags) ? data.preferredTags : [],
    };
  } catch (e) {
    console.warn('[recommendationService] /user_events 실패:', e.message);
    return null;
  }
}

/**
 * 나의 먹거리 일기 — 그 user_id 의 DB 검색 세션별 {태그, 선택 음식, 클릭 음식}.
 *
 * 백엔드 /user_diary 호출 — recommend.db 에 실제 저장된 내 태그 검색·선택 이력.
 * 각 entry: {sessionId, timestamp, tags:[], selected:[], clicked:[]}.
 */
export async function getUserDiary(userId = 1, limit = 20) {
  try {
    const res = await fetch(`${API_BASE}/user_diary?user_id=${userId}&limit=${limit}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return Array.isArray(data.entries) ? data.entries : [];
  } catch (e) {
    console.warn('[recommendationService] /user_diary 실패:', e.message);
    return [];
  }
}
