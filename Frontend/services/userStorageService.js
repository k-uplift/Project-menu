/**
 * userStorageService.js
 *
 * 사용자 데이터 영구 저장 (AsyncStorage 기반)
 *
 * 저장 항목:
 *  - 최근 검색 키워드 (최대 50개)
 *  - 최근 추천 메뉴 (최대 10개)
 *  - 사용자 선호 태그 (검색 키워드 빈도 자동 집계)
 *
 * 좋아요 기능 제거 (CF 신호 단일화 — implicit-only):
 *  메뉴 선택(1점) / 최종 선택=길찾기·배달(2점)으로 사용자 의도 표현.
 *  좋아요는 explicit이라 implicit 신호와 가중치 합산이 임의 → 제거.
 *  선호 태그는 *사용자가 직접 입력한 검색어*의 추출 태그 빈도로 잡는다 — 자기 발화가 좋아요 한 번 누름보다 더 명확한 선호 표현.
 *
 * 추후 백엔드 연결 시:
 *  - 함수 시그니처는 그대로 유지
 *  - 내부만 fetch 로 교체 (예: GET /api/users/me/searches)
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

const KEYS = {
  recentSearches: '@menu/recent_searches',
  recentFoods: '@menu/recent_foods',
};

// 검색 이력은 마이페이지 통계(선호 태그·맛 스펙트럼·자주 쓰는 표현)의 source라
// 충분히 누적되도록 50개. 추천 이력은 단순 표시용이라 10개 유지.
const MAX_RECENT_SEARCHES = 50;
const MAX_RECENT_FOODS = 10;

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
 * 최근 검색 항목 추가 — '나의 먹거리 일기' 한 칸.
 * 쿼리 + 추출 태그 + 그때 추천받은 메뉴를 함께 묶어 자기완결적 일기 entry로 저장.
 * @param {string} originalText  사용자가 입력한 쿼리 원문
 * @param {{label:string}[]} keywords  extract 결과 키워드 (라벨만 저장)
 * @param {{name:string, tags?:string[]}[]} [foods]  그 검색으로 추천받은 메뉴 상위 몇 개
 */
export async function addRecentSearch(originalText, keywords, foods = []) {
  const list = await readJSON(KEYS.recentSearches, []);
  const entry = {
    id: `search-${Date.now()}`,
    originalText,
    keywords: keywords.map((k) => k.label),
    foods: (foods || []).slice(0, 3).map((f) => ({
      name: f.name,
      tags: (f.tags || []).slice(0, 3),
    })),
    timestamp: Date.now(),
  };

  const filtered = list.filter((item) => item.originalText !== originalText);
  const newList = [entry, ...filtered].slice(0, MAX_RECENT_SEARCHES);
  await writeJSON(KEYS.recentSearches, newList);
}

export async function getRecentSearches() {
  return readJSON(KEYS.recentSearches, []);
}

// =====================================================
// 최근 추천 메뉴
// =====================================================

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
  const newList = [entry, ...filtered].slice(0, MAX_RECENT_FOODS);
  await writeJSON(KEYS.recentFoods, newList);
}

export async function getRecentFoods() {
  return readJSON(KEYS.recentFoods, []);
}

// =====================================================
// 사용자 선호 태그 (검색 키워드 빈도 자동 집계)
// =====================================================

/**
 * 검색 키워드에서 추출된 태그들의 빈도 집계.
 * 같은 사용자가 "얼큰한 국물" 5번 검색했으면 #얼큰한 5, #국물있는 5.
 *
 * 기존 좋아요 기반 → 검색 기반으로 source 교체.
 * 사용자가 직접 입력한 *말*이 한 번의 ♥ 클릭보다 의도가 명확함.
 *
 * @returns {Promise<Array<{tag: string, count: number}>>}
 */
export async function getPreferredTags() {
  const searches = await readJSON(KEYS.recentSearches, []);
  const tagMap = new Map();

  searches.forEach((s) => {
    (s.keywords || []).forEach((tag) => {
      tagMap.set(tag, (tagMap.get(tag) || 0) + 1);
    });
  });

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
  ]);
}
