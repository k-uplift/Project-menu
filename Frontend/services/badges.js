/**
 * badges.js — 마이페이지 칭호 시스템
 *
 * 5 카테고리 29종 칭호 (5/29 사용자 결정, CLAUDE.md §5.13 (7)):
 *   A. 맛 속성 (시드 14개 매핑)        8종
 *   B. 장르 (11개 카테고리)            6종
 *   C. 특정 음식 (363 vocab)          6종
 *   D. 행동 패턴 (시간/다양성/반복)    6종
 *   E. 희귀·메타                       3종
 *
 * 데이터 source:
 *   - behaviorTrackingService.getBehaviorEvents() — 클릭/길찾기/배달 누적
 *   - userStorageService.getRecentSearches()      — 새벽 사냥꾼(D)용
 *
 * "최종 선택" = navigate_click 또는 delivery_click (+2점)
 * "관심"      = food_card_click (+1점)
 *
 * 사용:
 *   const events = await getBehaviorEvents();
 *   const searches = await getRecentSearches();
 *   const earned = getEarnedBadges(events, searches);
 *   // earned = [{id, category, name, icon, description, ...}, ...]
 */

// =====================================================
// 칭호 데이터 — 29종 메타데이터 + 부여 조건 함수
// =====================================================

// 조건 함수의 입력:
//   stats = computeStats(events, searches)
// 출력: { ok: boolean, progress?: {current, target} }
//   ok: 달성 여부
//   progress: 미달성 시 진행률 표시용 (optional)

export const BADGES = [
  // ── A. 맛 속성 (시드 14개) — 8종 ─────────────────────────────────
  {
    id: 'spicy',
    category: 'A',
    name: '칼칼함 마니아',
    icon: '🌶',
    description: '얼큰한 메뉴 최종 선택 5회+',
    check: (s) => count(s.seedCounts['얼큰한'], 5),
  },
  {
    id: 'soup',
    category: 'A',
    name: '국물 애호가',
    icon: '🍲',
    description: '국물있는 + 한식국물탕 최종 선택 5회+',
    check: (s) => count(
      Math.min(s.seedCounts['국물있는'] || 0, s.koreanSoupCount || 0)
        || s.seedCounts['국물있는'] || 0,  // 시드만 있으면 인정 (느슨)
      5
    ),
  },
  {
    id: 'hearty',
    category: 'A',
    name: '든든한 한 끼파',
    icon: '🍚',
    description: '든든한 메뉴 최종 선택 5회+',
    check: (s) => count(s.seedCounts['든든한'], 5),
  },
  {
    id: 'mild',
    category: 'A',
    name: '담백 미식가',
    icon: '🥗',
    description: '담백한 메뉴 최종 선택 5회+',
    check: (s) => count(s.seedCounts['담백한'], 5),
  },
  {
    id: 'hangover',
    category: 'A',
    name: '해장 전문가',
    icon: '🍻',
    description: '해장 메뉴 최종 선택 3회+ (희소 시드)',
    check: (s) => count(s.seedCounts['해장'], 3),
  },
  {
    id: 'rich',
    category: 'A',
    name: '진한 맛 추구자',
    icon: '🔥',
    description: '진한 메뉴 최종 선택 5회+',
    check: (s) => count(s.seedCounts['진한'], 5),
  },
  {
    id: 'light',
    category: 'A',
    name: '가벼운 한 입파',
    icon: '☁️',
    description: '가벼운 메뉴 최종 선택 5회+',
    check: (s) => count(s.seedCounts['가벼운'], 5),
  },
  {
    id: 'midnight',
    category: 'A',
    name: '야식러',
    icon: '🌙',
    description: '야식 메뉴를 22~02시 사이 최종 선택 3회+',
    check: (s) => count(s.midnightYasikCount, 3),
  },

  // ── B. 장르 (카테고리) — 6종 ────────────────────────────────────
  {
    id: 'korean',
    category: 'B',
    name: '한식 마스터',
    icon: '🇰🇷',
    description: '한식(국물탕/고기/면밥/조림찜) 최종 선택 10회+',
    check: (s) => count(s.categoryCounts['한식'], 10),
  },
  {
    id: 'japanese',
    category: 'B',
    name: '일식 애호가',
    icon: '🍣',
    description: '일식 최종 선택 5회+',
    check: (s) => count(s.categoryCounts['일식'], 5),
  },
  {
    id: 'chinese',
    category: 'B',
    name: '중식 탐험가',
    icon: '🥟',
    description: '중식 최종 선택 5회+',
    check: (s) => count(s.categoryCounts['중식'], 5),
  },
  {
    id: 'western',
    category: 'B',
    name: '양식 미식가',
    icon: '🍝',
    description: '양식 최종 선택 5회+',
    check: (s) => count(s.categoryCounts['양식'], 5),
  },
  {
    id: 'chicken',
    category: 'B',
    name: '치킨 헌터',
    icon: '🍗',
    description: '치킨 카테고리 최종 선택 3회+',
    check: (s) => count(s.categoryCounts['치킨'], 3),
  },
  {
    id: 'dessert',
    category: 'B',
    name: '디저트 러버',
    icon: '🍰',
    description: '디저트 최종 선택 5회+',
    check: (s) => count(s.categoryCounts['디저트'], 5),
  },

  // ── C. 특정 음식 (kind) — 6종 ───────────────────────────────────
  {
    id: 'ramen',
    category: 'C',
    name: '라면 충신',
    icon: '🍜',
    description: '라면 최종 선택 3회+',
    check: (s) => count(s.kindCounts['라면'], 3),
  },
  {
    id: 'tteokbokki',
    category: 'C',
    name: '떡볶이 마니아',
    icon: '🌶',
    description: '떡볶이 최종 선택 3회+',
    check: (s) => count(s.kindCounts['떡볶이'], 3),
  },
  {
    id: 'meat',
    category: 'C',
    name: '고기파',
    icon: '🥩',
    description: '고기류(삼겹살·갈비·스테이크 등) 최종 선택 5회+',
    check: (s) => count(sumKinds(s, MEAT_KINDS), 5),
  },
  {
    id: 'sashimi',
    category: 'C',
    name: '회 마니아',
    icon: '🐟',
    description: '회류(초밥·사시미·회덮밥 등) 최종 선택 3회+',
    check: (s) => count(sumKinds(s, SASHIMI_KINDS), 3),
  },
  {
    id: 'noodle',
    category: 'C',
    name: '면 러버',
    icon: '🥢',
    description: '면류(라면·우동·짜장면·파스타 등) 최종 선택 5회+',
    check: (s) => count(sumKinds(s, NOODLE_KINDS), 5),
  },
  {
    id: 'rice',
    category: 'C',
    name: '밥심러',
    icon: '🍚',
    description: '밥류(비빔밥·덮밥·볶음밥 등) 최종 선택 5회+',
    check: (s) => count(sumKinds(s, RICE_KINDS), 5),
  },

  // ── D. 행동 패턴 — 6종 ───────────────────────────────────────────
  {
    id: 'morning',
    category: 'D',
    name: '아침형 인간',
    icon: '🌅',
    description: '6~10시 최종 선택 5회+',
    check: (s) => count(s.hourBuckets.morning, 5),
  },
  {
    id: 'lunch',
    category: 'D',
    name: '점심 인사이더',
    icon: '☀️',
    description: '11~14시 최종 선택 10회+',
    check: (s) => count(s.hourBuckets.lunch, 10),
  },
  {
    id: 'dawn',
    category: 'D',
    name: '새벽 사냥꾼',
    icon: '🌃',
    description: '0~5시 검색 3회+',
    check: (s) => count(s.dawnSearches, 3),
  },
  {
    id: 'explorer',
    category: 'D',
    name: '새로운 맛 탐험가',
    icon: '🧭',
    description: '다른 카테고리 5종 이상에서 최종 선택',
    check: (s) => count(s.uniqueCategories, 5),
  },
  {
    id: 'regular',
    category: 'D',
    name: '단골',
    icon: '❤️',
    description: '같은 식당 최종 선택 3회+',
    check: (s) => count(s.maxStoreCount, 3),
  },
  {
    id: 'decisive',
    category: 'D',
    name: '결정파',
    icon: '🎯',
    description: '검색 후 첫 추천 카드를 그대로 최종 선택 비율 70%+ (10회 이상 검색 시)',
    // 구현 한계: 현재 이벤트 payload에 '검색→첫 카드 선택' 시그널이 없음. 추후 검색-선택
    // 연결 시 활성화. 일단 항상 false.
    check: () => ({ ok: false, progress: { current: 0, target: 10 } }),
  },

  // ── E. 메타 — 3종 ───────────────────────────────────────────────
  {
    id: 'master',
    category: 'E',
    name: '만능 미식가',
    icon: '🌟',
    description: '14개 시드 중 10개 이상에서 최종 선택 1회+',
    check: (s) => count(s.uniqueSeeds, 10),
  },
  {
    id: 'specialist',
    category: 'E',
    name: '한 우물 파',
    icon: '🎭',
    description: '한 시드 태그가 최종 선택의 60% 이상 점유',
    check: (s) => {
      if (s.totalSeedHits < 10) return { ok: false }; // 표본 너무 작음
      return { ok: s.topSeedShare >= 0.6 };
    },
  },
  {
    id: 'watcher',
    category: 'E',
    name: '눈팅러',
    icon: '👁',
    description: '카드 클릭 20회+ vs 최종 선택 5회 미만 (관심↔실행 갭)',
    check: (s) => ({
      ok: (s.clickCount || 0) >= 20 && (s.finalCount || 0) < 5,
    }),
  },
];

// =====================================================
// kind 묶음 (C 칭호용)
// =====================================================

const MEAT_KINDS = new Set([
  '삼겹살', '오겹살', '목살', '갈비', '우대갈비', '등심', '차돌박이',
  '막창', '곱창', '대창', '항정살', '살치살', '안창살', '토시살',
  '꽃등심', '부채살', 'LA갈비', '양념갈비', '제육볶음', '불고기',
  '보쌈', '족발', '수육', '갈비찜', '닭갈비', '찜닭', '스테이크',
]);

const SASHIMI_KINDS = new Set([
  '스시', '초밥', '사시미', '회', '오마카세', '니기리', '마키', '롤',
  '회덮밥', '참치회', '광어회', '연어회', '사시미동',
]);

const NOODLE_KINDS = new Set([
  '라면', '라멘', '우동', '소바', '메밀', '쌀국수', '짜장면', '짜장',
  '간짜장', '짬뽕', '삼선짬뽕', '차돌짬뽕', '칼국수', '잔치국수', '쫄면',
  '막국수', '메밀국수', '냉면', '비빔국수', '쟁반국수', '국수', '콩국수',
  '파스타', '스파게티', '까르보나라', '크림파스타', '로제파스타',
  '아라비아따', '뽀모도로', '라자냐', '뇨끼', '페투치네', '츠케멘',
  '마제소바', '야키소바', '기스면',
]);

const RICE_KINDS = new Set([
  '비빔밥', '김치볶음밥', '새우볶음밥', '볶음밥', '김밥', '덮밥',
  '제육덮밥', '소고기덮밥', '오므라이스', '돌솥비빔밥', '주먹밥',
  '곤드레밥', '카레', '카레라이스', '짜장밥', '오징어덮밥', '회덮밥',
  '가츠동', '카츠동', '규동', '오야꼬동', '텐동', '장어덮밥',
]);

// 카테고리 11개 → 상위 묶음 (B 한식 마스터)
const KOREAN_CATEGORIES = new Set([
  '한식국물탕', '한식고기', '한식면밥', '한식조림찜',
]);

function sumKinds(stats, kindSet) {
  let n = 0;
  for (const [kind, cnt] of Object.entries(stats.kindCounts)) {
    if (kindSet.has(kind)) n += cnt;
  }
  return n;
}

function count(current, target) {
  const c = current || 0;
  return { ok: c >= target, progress: { current: c, target } };
}

// =====================================================
// stats 집계 — 이벤트·검색 리스트에서 칭호 판정용 통계 만들기
// =====================================================

/**
 * @param {Array} events  - getBehaviorEvents() 결과
 * @param {Array} searches - getRecentSearches() 결과
 * @returns {Object} stats
 */
export function computeStats(events = [], searches = []) {
  const stats = {
    // 시드별 카운트 — A·E
    seedCounts: {},
    // 카테고리별 카운트 — B (한식 4개는 '한식'으로 합산도 함께)
    categoryCounts: {},
    koreanSoupCount: 0,  // 카테고리=한식국물탕 (국물 애호가용)
    // kind별 카운트 — C
    kindCounts: {},
    // 시간대 카운트 — D
    hourBuckets: { morning: 0, lunch: 0, midnight: 0 },
    midnightYasikCount: 0,  // 야식 태그 + 22~02시
    dawnSearches: 0,        // 0~5시 검색 (recentSearches 기반)
    // 다양성 — D, E
    uniqueCategories: 0,
    uniqueSeeds: 0,
    maxStoreCount: 0,
    // 관심 vs 실행 — E
    clickCount: 0,
    finalCount: 0,
    // 시드 점유율 — E
    totalSeedHits: 0,
    topSeedShare: 0,
  };

  const seenCategories = new Set();
  const storeCount = {};

  for (const ev of events) {
    const isFinal = ev.type === 'navigate_click' || ev.type === 'delivery_click';
    const isClick = ev.type === 'food_card_click';
    if (isFinal) stats.finalCount++;
    if (isClick) stats.clickCount++;

    // 최종 선택만 칭호 산정에 사용 (D 결정파 외)
    if (!isFinal) continue;

    const p = ev.payload || {};
    const tags = p.foodTags || [];
    const category = p.restaurantCategory;
    const kind = p.foodName;
    const storeId = p.restaurantId;
    const hour = new Date(ev.timestamp).getHours();

    // 시드 카운트
    for (const t of tags) {
      stats.seedCounts[t] = (stats.seedCounts[t] || 0) + 1;
      stats.totalSeedHits++;
    }

    // 카테고리 카운트 — '한식국물탕' 등 세부 → '한식'으로도 합산
    if (category) {
      stats.categoryCounts[category] = (stats.categoryCounts[category] || 0) + 1;
      if (KOREAN_CATEGORIES.has(category)) {
        stats.categoryCounts['한식'] = (stats.categoryCounts['한식'] || 0) + 1;
      }
      if (category === '한식국물탕') stats.koreanSoupCount++;
      seenCategories.add(category);
    }

    // kind 카운트
    if (kind) stats.kindCounts[kind] = (stats.kindCounts[kind] || 0) + 1;

    // 시간대
    if (hour >= 6 && hour <= 10) stats.hourBuckets.morning++;
    if (hour >= 11 && hour <= 14) stats.hourBuckets.lunch++;
    if (hour >= 22 || hour <= 2) {
      stats.hourBuckets.midnight++;
      if (tags.includes('야식')) stats.midnightYasikCount++;
    }

    // 식당 빈도 (단골)
    if (storeId) {
      storeCount[storeId] = (storeCount[storeId] || 0) + 1;
      stats.maxStoreCount = Math.max(stats.maxStoreCount, storeCount[storeId]);
    }
  }

  // 검색 시간대 (D 새벽 사냥꾼)
  for (const s of searches) {
    if (!s.timestamp) continue;
    const hour = new Date(s.timestamp).getHours();
    if (hour >= 0 && hour <= 5) stats.dawnSearches++;
  }

  // 파생 통계
  stats.uniqueCategories = seenCategories.size;
  stats.uniqueSeeds = Object.keys(stats.seedCounts).length;
  if (stats.totalSeedHits > 0) {
    const topCount = Math.max(...Object.values(stats.seedCounts));
    stats.topSeedShare = topCount / stats.totalSeedHits;
  }

  return stats;
}

// =====================================================
// 메인 API — 부여된 칭호 + 진행률
// =====================================================

/**
 * 달성한 칭호와 모든 칭호의 진행률 반환.
 *
 * @param {Array} events
 * @param {Array} searches
 * @returns {{earned: Array, all: Array}}
 *   earned = 달성한 칭호만 (BADGES 형태)
 *   all = 29개 전체 (각각 + earned 여부 + progress)
 */
export function getEarnedBadges(events = [], searches = []) {
  const stats = computeStats(events, searches);
  const all = BADGES.map((b) => {
    const r = b.check(stats);
    return { ...b, earned: r.ok, progress: r.progress || null };
  });
  return {
    earned: all.filter((b) => b.earned),
    all,
    stats,  // 디버그용 노출
  };
}
