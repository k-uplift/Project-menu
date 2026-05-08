/**
 * recommendationService.js
 *
 * 키워드(+컨텍스트) → 음식 추천
 *
 * 추가 기능:
 *  - 시간대/날씨 자동 감지 후 추천 이유에 반영
 *    → "비 오는 저녁 시간대 선호도가 높아요" 같은 동적 문구 생성
 *  - 사용자 가중치 (날씨/시간/취향) 반영 가능 구조
 */

import { MOCK_FOODS } from '../data/foods.mock';
import {
  getCurrentTimeContext,
  getCurrentWeather,
  getCombinedContextReason,
} from './contextService';

/**
 * @typedef {Object} RecommendContext
 * @property {Object} [timeCtx]                    - getCurrentTimeContext() 결과
 * @property {Object} [weatherCtx]                 - getCurrentWeather() 결과
 * @property {{weather:number, time:number, taste:number}} [weights]
 * @property {{soup:'yes'|'no'|'any', people:'solo'|'2'|'3+', calorie:'low'|'mid'|'high'}} [conditions]
 * @property {number} [refreshSeed]
 */

/**
 * 음식 추천 받기
 *
 * @param {import('../types').Keyword[]} keywords
 * @param {RecommendContext} [context]
 * @returns {Promise<import('../types').FoodItem[]>}
 */
export async function getFoodRecommendations(keywords, context = {}) {
  await delay(600);

  if (!keywords || keywords.length === 0) {
    return [];
  }

  // 컨텍스트가 안 들어오면 자동 감지
  const timeCtx = context.timeCtx || getCurrentTimeContext();
  const weatherCtx = context.weatherCtx || (await getCurrentWeather());
  const weights = context.weights || { weather: 50, time: 50, taste: 70 };
  const conditions = context.conditions || {};

  const labels = keywords.map((k) => k.label);
  const seed = context.refreshSeed || 0;

  const scored = MOCK_FOODS.map((food, idx) => {
    const matched = food.tags.filter((t) => labels.includes(t));
    const matchRate = labels.length > 0 ? matched.length / labels.length : 0;

    // 기본 점수
    let dynamicScore = food.score * 0.7 + matchRate * 100 * 0.3;

    // 가중치 적용 — 사용자가 슬라이더로 조절한 영향력 반영
    // (시연용 간단 모델, 실제 추천 엔진에서는 벡터 가중합으로 처리)
    const tasteBoost = (matchRate * weights.taste) / 100;
    dynamicScore = dynamicScore * 0.7 + tasteBoost * 30;

    // 조건 필터 (국물 유무, 칼로리 등)
    if (conditions.soup === 'yes' && !food.tags.includes('국물있는')) {
      dynamicScore *= 0.5;
    } else if (conditions.soup === 'no' && food.tags.includes('국물있는')) {
      dynamicScore *= 0.5;
    }
    if (conditions.calorie === 'low' && food.tags.includes('든든한')) {
      dynamicScore *= 0.7;
    }

    // 새로고침 시드
    if (seed > 0) {
      const variance = Math.sin(seed * 9.7 + idx * 2.3) * 7;
      dynamicScore += variance;
    }

    // 자동 생성 컨텍스트 문구 — 키워드/시간/날씨 조합
    const dynamicContextNote = getCombinedContextReason(timeCtx, weatherCtx);

    return {
      ...food,
      score: Math.max(50, Math.min(99, Math.round(dynamicScore))),
      reason: {
        ...food.reason,
        matchedKeywords:
          matched.length > 0 ? matched : food.reason.matchedKeywords.slice(0, 1),
        // 동적으로 생성된 컨텍스트 문구로 교체
        contextNote: dynamicContextNote,
      },
    };
  });

  scored.sort((a, b) => b.score - a.score);
  return scored;
}

/**
 * "나를 위한 추천" — CF 기반 정렬
 */
export async function getPersonalizedRecommendations(keywords, context = {}) {
  const base = await getFoodRecommendations(keywords, context);

  const seed = context.refreshSeed || 0;
  const adjusted = base.map((food, idx) => {
    if (seed === 0) return food;
    const variance = Math.sin(seed * 5.1 + idx * 3.7) * 0.06;
    return {
      ...food,
      reason: {
        ...food.reason,
        cfScore: Math.max(0.5, Math.min(0.99, food.reason.cfScore + variance)),
      },
    };
  });

  return [...adjusted].sort((a, b) => b.reason.cfScore - a.reason.cfScore);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
