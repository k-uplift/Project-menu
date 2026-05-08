/**
 * restaurantService.js
 *
 * 선택된 음식 → 음식점 리스트
 *
 * 추가된 기능:
 *  - 한성대 기숙사 기준 거리 자동 계산 (Haversine)
 *  - 도보 시간 자동 계산 (4 km/h 기준)
 */

import { MOCK_RESTAURANTS_BY_FOOD, DEFAULT_RESTAURANTS } from '../data/restaurants.mock';
import {
  BASE_LOCATION,
  haversineDistance,
  walkMinutesFromKm,
} from './contextService';

/**
 * @typedef {'distance'|'cf'} SortMode
 */

/**
 * 특정 음식을 제공하는 음식점 목록을 가져옴
 *
 * @param {string} foodId
 * @param {Object} [options]
 * @param {SortMode} [options.sort='distance'] - 정렬 기준
 * @param {Object} [options.userLocation] - 사용자 위치 {latitude, longitude}, 없으면 BASE_LOCATION 사용
 * @returns {Promise<import('../types').Restaurant[]>}
 */
export async function getRestaurantsByFood(foodId, options = {}) {
  const { sort = 'distance', userLocation } = options;

  // === [실제 API 연결 시 이 부분 교체] ===
  //
  // const res = await fetch(
  //   `https://api.menu-app.com/restaurants?food=${foodId}&lat=${lat}&lon=${lon}&sort=${sort}`
  // );
  // return await res.json();
  //
  // ======================================

  await delay(500);

  const list = MOCK_RESTAURANTS_BY_FOOD[foodId] || DEFAULT_RESTAURANTS;

  // 사용자 좌표 (없으면 한성대 기숙사 기준)
  const userLat = userLocation?.latitude || BASE_LOCATION.latitude;
  const userLon = userLocation?.longitude || BASE_LOCATION.longitude;

  // 각 음식점에 대해 거리/도보시간 자동 계산
  const enriched = list.map((rest) => {
    let distanceKm = rest.distanceKm; // fallback
    let walkMin = rest.walkMin;       // fallback

    if (rest.latitude && rest.longitude) {
      distanceKm = haversineDistance(
        userLat,
        userLon,
        rest.latitude,
        rest.longitude
      );
      walkMin = walkMinutesFromKm(distanceKm);
    }

    return {
      ...rest,
      distanceKm: Math.round(distanceKm * 10) / 10, // 0.1 단위
      walkMin,
    };
  });

  // 정렬
  if (sort === 'distance') {
    enriched.sort((a, b) => a.distanceKm - b.distanceKm);
  } else if (sort === 'cf') {
    enriched.sort((a, b) => b.cfMatch - a.cfMatch);
  }

  return enriched;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
