/**
 * userStorageService.js
 *
 * 사용자 데이터 영구 저장 (AsyncStorage 기반)
 *
 * 저장 항목:
 *  - 최근 검색 키워드 (최대 10개)
 *  - 최근 추천 메뉴 (최대 10개)
 *  - 좋아요한 메뉴 (제한 없음)
 *  - 사용자 선호 태그 (좋아요 + 클릭 이력 기반 자동 집계)
 *
 * 추후 백엔드 연결 시:
 *  - 함수 시그니처는 그대로 유지
 *  - 내부만 fetch 로 교체 (예: GET /api/users/me/likes)
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

// 저장 키 — prefix로 그룹핑
const KEYS = {
  recentSearches: '@menu/recent_searches',
  recentFoods: '@menu/recent_foods',
  likedFoods: '@menu/liked_foods',
};

// 리스트 최대 길이
const MAX_RECENT = 10;

// === 내부 유틸 ===
async function readJSON(key, fallback = []) {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    console.warn(`[userStorage] read ${key} failed:`, e);
    return fallback;
  }
}

async function writeJSON(key, value) {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.warn(`[userStorage] write ${key} failed:`, e);
  }
}

// =====================================================
// 최근 검색 키워드
// =====================================================

/**
 * 최근 검색 항목 추가
 * @param {Object} entry - { originalText, keywords, timestamp }
 */
export async function addRecentSearch(originalText, keywords) {
  const list = await readJSON(KEYS.recentSearches, []);
  const entry = {
    id: `search-${Date.now()}`,
    originalText,
    keywords: keywords.map((k) => k.label), // 라벨만 저장 (간단하게)
    timestamp: Date.now(),
  };

  // 같은 텍스트가 이미 있으면 제거 후 맨 앞에 다시 추가
  const filtered = list.filter((item) => item.originalText !== originalText);
  const newList = [entry, ...filtered].slice(0, MAX_RECENT);
  await writeJSON(KEYS.recentSearches, newList);
}

/**
 * 최근 검색 목록 가져오기
 */
export async function getRecentSearches() {
  return readJSON(KEYS.recentSearches, []);
}

// =====================================================
// 최근 추천 메뉴
// =====================================================

/**
 * 최근 추천받은 메뉴 추가
 * @param {Object} food - FoodItem 객체
 */
export async function addRecentFood(food) {
  const list = await readJSON(KEYS.recentFoods, []);
  const entry = {
    id: food.id,
    name: food.name,
    emoji: food.emoji,
    tags: food.tags,
    timestamp: Date.now(),
  };

  const filtered = list.filter((item) => item.id !== food.id);
  const newList = [entry, ...filtered].slice(0, MAX_RECENT);
  await writeJSON(KEYS.recentFoods, newList);
}

export async function getRecentFoods() {
  return readJSON(KEYS.recentFoods, []);
}

// =====================================================
// 좋아요한 메뉴
// =====================================================

/**
 * 좋아요 토글
 * @returns {Promise<boolean>} 토글 후 좋아요 상태 (true=좋아요)
 */
export async function toggleLikeFood(food) {
  const list = await readJSON(KEYS.likedFoods, []);
  const existIdx = list.findIndex((item) => item.id === food.id);

  if (existIdx >= 0) {
    // 이미 있으면 제거
    list.splice(existIdx, 1);
    await writeJSON(KEYS.likedFoods, list);
    return false;
  } else {
    // 없으면 추가
    const entry = {
      id: food.id,
      name: food.name,
      emoji: food.emoji,
      tags: food.tags,
      likedAt: Date.now(),
    };
    list.unshift(entry); // 맨 앞에
    await writeJSON(KEYS.likedFoods, list);
    return true;
  }
}

export async function getLikedFoods() {
  return readJSON(KEYS.likedFoods, []);
}

/**
 * 특정 음식이 좋아요 되어있는지 확인
 */
export async function isFoodLiked(foodId) {
  const list = await readJSON(KEYS.likedFoods, []);
  return list.some((item) => item.id === foodId);
}

// =====================================================
// 사용자 선호 태그 (자동 집계)
// =====================================================

/**
 * 좋아요한 메뉴들의 태그를 집계해 선호 태그 리스트 반환
 * (별도 저장하지 않고 매번 계산 — 데이터 정합성 유지)
 *
 * @returns {Promise<Array<{tag: string, count: number}>>}
 */
export async function getPreferredTags() {
  const liked = await readJSON(KEYS.likedFoods, []);
  const tagMap = new Map();

  liked.forEach((food) => {
    (food.tags || []).forEach((tag) => {
      tagMap.set(tag, (tagMap.get(tag) || 0) + 1);
    });
  });

  // 빈도순 정렬
  return Array.from(tagMap.entries())
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count);
}

// =====================================================
// 전체 데이터 초기화 (개발/디버그용)
// =====================================================

export async function clearAllUserData() {
  await Promise.all([
    AsyncStorage.removeItem(KEYS.recentSearches),
    AsyncStorage.removeItem(KEYS.recentFoods),
    AsyncStorage.removeItem(KEYS.likedFoods),
  ]);
}
