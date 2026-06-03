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
import { getCurrentUser } from './authService';


async function getDefaultUserId() {
  try {
    const u = await getCurrentUser();
    return u?.user_id ?? 1;
  } catch { return 1; }
}

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
  // 로그인 사용자의 user_id 를 식당 cfScore(취향 매칭)에 반영. 비로그인이면 1(Alice).
  const defaultUid = await getDefaultUserId();
  const { sort = 'distance', userLocation, query, userId = defaultUid } = options;

  // 백엔드는 q + kind 둘 다 필수. q가 없으면 종류 이름을 자기 자신을 쿼리로.
  const kind = food?.name || '';
  const q = (query && query.trim()) || kind;
  if (!kind) return [];

  let stores = [];
  try {
    const url =
      `${API_BASE}/restaurants` +
      `?q=${encodeURIComponent(q)}` +
      `&kind=${encodeURIComponent(kind)}` +
      `&user_id=${userId}`;
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
      // cfMatch (0~1) — 백엔드가 user_id 기반 식당 cfScore 정규화해서 제공.
      cfMatch: rest.cfMatch ?? 0,
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
    // 백엔드 cfScore 내림차순 — 식당 메뉴들의 *내 유사 사용자 행동 가중치 합*.
    // 동률이면 거리순(가까운 곳)으로 fallback — 자연 순서.
    enriched.sort((a, b) => {
      const diff = (b.cfScore || 0) - (a.cfScore || 0);
      if (diff !== 0) return diff;
      // tie-breaker: 거리
      const da = a.distanceKm ?? Infinity;
      const db = b.distanceKm ?? Infinity;
      return da - db;
    });
  }

  return enriched;
}

/**
 * 한 식당의 *전체* 메뉴 가져오기 — RestaurantDetail용.
 *
 * `getRestaurantsByFood`가 반환하는 `menuItems`는 *선택한 kind에 매칭된*
 * 메뉴들만 들어 있어 식당 상세 화면에선 "메뉴가 적다"는 인상을 줌. 이 함수가
 * 그 식당의 모든 메뉴(태그·가격·종류 포함)를 별도로 받아와, 화면이
 * *추천 메뉴 강조 + 전체 메뉴 목록* 두 섹션으로 자연스럽게 구성된다.
 *
 * @param {number|string} storeId
 * @returns {Promise<Array<{name, price, tags, kind}>>}
 */
export async function getAllMenusByStore(storeId) {
  if (!storeId) return [];
  try {
    const res = await fetch(`${API_BASE}/restaurants/${storeId}/menus`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return Array.isArray(data.menus) ? data.menus : [];
  } catch (e) {
    console.warn('[restaurantService] /restaurants/:id/menus 실패:', e.message);
    return [];
  }
}
