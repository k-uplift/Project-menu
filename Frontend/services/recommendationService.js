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
 * 음식 추천 받기
 *
 * @param {import('../types').Keyword[]} keywords
 * @param {RecommendContext} [context]
 * @returns {Promise<import('../types').FoodItem[]>}
 */
export async function getFoodRecommendations(keywords, context = {}) {
  if (!keywords || keywords.length === 0) return [];

  const q =
    (context.originalText && context.originalText.trim()) ||
    keywords.map((k) => k.label).join(' ');

  let kinds = [];
  try {
    const url = `${API_BASE}/foods?q=${encodeURIComponent(q)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    kinds = Array.isArray(data.kinds) ? data.kinds : [];
  } catch (e) {
    console.warn('[recommendationService] /foods fetch 실패:', e.message);
    return [];
  }

  // 동적 contextNote(시간·날씨) — 백엔드 응답에는 항상 null이라 클라가 채움
  const timeCtx = context.timeCtx || getCurrentTimeContext();
  const weatherCtx = context.weatherCtx || (await getCurrentWeather());
  const dynamicContextNote = getCombinedContextReason(timeCtx, weatherCtx);

  return kinds.map((food) => ({
    ...food,
    reason: {
      ...food.reason,
      contextNote: dynamicContextNote,
    },
  }));
}

/**
 * "나를 위한 추천" — CF 기반 정렬
 *
 * 현재 CF 백엔드 미구현 — base와 동일 결과. CF 엔드포인트가 붙으면
 * 별도 fetch로 교체 예정. 시그니처는 유지해서 화면 변경 0.
 */
export async function getPersonalizedRecommendations(keywords, context = {}) {
  return getFoodRecommendations(keywords, context);
}
