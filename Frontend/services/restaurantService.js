/**
 * restaurantService.js
 *
 * 선택된 음식(=음식 종류) → 음식점 리스트
 *
 * 백엔드(FastAPI /restaurants) 호출:
 *  - 쿼리(q): 1차 검색의 자연어 원문. 사용자 취향이 식당 점수에 그대로 반영됨
 *  - 종류(kind): food.name (백엔드 vocab과 같은 한국어 단어)
 *  - 응답의 stores[]가 Restaurant 계약과 일치 (백엔드 to_store_group())
 *
 * 거리/도보 시간은 클라이언트 사이드 계산 (한성대 기숙사 기준 Haversine, 4 km/h).
 * 백엔드는 좌표(EPSG:5181 → WGS84 변환)만 제공.
 */

import { API_BASE } from '../constants/api';
import {
  BASE_LOCATION,
  haversineDistance,
  walkMinutesFromKm,
} from './contextService';

/**
 * @typedef {'distance'|'cf'} SortMode
 */

/**
 * 음식 종류를 파는 음식점 목록을 가져옴
 *
 * @param {import('../types').FoodItem} food   - 1차에서 선택한 음식. food.name이 kind로 사용됨
 * @param {Object} [options]
 * @param {SortMode} [options.sort='distance']
 * @param {{latitude:number, longitude:number}} [options.userLocation]
 * @param {string} [options.query]             - 1차 검색의 자연어 원문 (취향 반영용)
 * @returns {Promise<import('../types').Restaurant[]>}
 */
export async function getRestaurantsByFood(food, options = {}) {
  const { sort = 'distance', userLocation, query } = options;

  // 백엔드는 q + kind 둘 다 필수. q가 없으면 종류 이름을 자기 자신을 쿼리로.
  const kind = food?.name || '';
  const q = (query && query.trim()) || kind;
  if (!kind) return [];

  let stores = [];
  try {
    const url =
      `${API_BASE}/restaurants` +
      `?q=${encodeURIComponent(q)}` +
      `&kind=${encodeURIComponent(kind)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    stores = Array.isArray(data.stores) ? data.stores : [];
  } catch (e) {
    console.warn('[restaurantService] /restaurants fetch 실패:', e.message);
    return [];
  }

  // 거리·도보 계산 (좌표가 null인 식당도 있음 — 그땐 그냥 null로 둠)
  const userLat = userLocation?.latitude ?? BASE_LOCATION.latitude;
  const userLon = userLocation?.longitude ?? BASE_LOCATION.longitude;

  const enriched = stores.map((rest) => {
    // 크롤링 데이터엔 없지만 UI(RestaurantCard·RestaurantDetail)가 참조하는 필드 stub.
    // rating은 .toFixed(1) 호출이 있어 undefined면 크래시 — 0 또는 null로 채움.
    const stubs = {
      rating: rest.rating ?? 0,
      reviewCount: rest.reviewCount ?? 0,
      delivery: rest.delivery ?? false,
      signature: rest.signature ?? false,
      cfMatch: rest.cfMatch ?? null,
    };

    if (rest.latitude == null || rest.longitude == null) {
      return { ...rest, ...stubs, distanceKm: null, walkMin: null };
    }
    const distanceKm = haversineDistance(
      userLat,
      userLon,
      rest.latitude,
      rest.longitude
    );
    return {
      ...rest,
      ...stubs,
      distanceKm: Math.round(distanceKm * 10) / 10, // 0.1 단위
      walkMin: walkMinutesFromKm(distanceKm),
    };
  });

  // 정렬: 좌표 없는 식당은 항상 뒤로
  if (sort === 'distance') {
    enriched.sort((a, b) => {
      if (a.distanceKm == null && b.distanceKm == null) return 0;
      if (a.distanceKm == null) return 1;
      if (b.distanceKm == null) return -1;
      return a.distanceKm - b.distanceKm;
    });
  } else if (sort === 'cf') {
    // CF 백엔드 미구현 — 임시로 점수 기준 정렬
    enriched.sort((a, b) => (b.score || 0) - (a.score || 0));
  }

  return enriched;
}
