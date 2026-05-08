/**
 * 음식 mock 데이터
 *
 * 추가된 필드: imageUrl (현재 null, 추후 실제 음식 이미지 URL로 교체)
 *
 * - 추천 이유에 [감성 키워드 매칭 / CF / 컨텍스트] 3종을 모두 포함
 * - emoji 필드는 호환성 유지용 (구버전 컴포넌트가 사용)
 *   FoodThumbnail 컴포넌트는 imageUrl이 없으면 카테고리 색상으로 자동 렌더
 */

export const MOCK_FOODS = [
  {
    id: 'food-001',
    name: '순두부찌개',
    emoji: '🍲',
    imageUrl: null,
    tags: ['따뜻한', '국물있는', '담백한', '얼큰한'],
    score: 95,
    reason: {
      matchedKeywords: ['따뜻한', '국물있는', '담백한'],
      cfScore: 0.91,
      cfDescription: '비슷한 취향의 사용자 91%가 비 오는 저녁에 이 메뉴를 선택했어요',
      contextNote: '흐린 날씨 · 저녁 시간대에 선호도가 높아요',
    },
  },
  {
    id: 'food-002',
    name: '칼국수',
    emoji: '🍜',
    imageUrl: null,
    tags: ['따뜻한', '국물있는', '담백한', '쫄깃한'],
    score: 88,
    reason: {
      matchedKeywords: ['따뜻한', '국물있는'],
      cfScore: 0.84,
      cfDescription: '"따뜻한 국물"을 찾는 사용자 84%가 함께 본 메뉴예요',
      contextNote: '쌀쌀한 날씨에 자주 선택돼요',
    },
  },
  {
    id: 'food-003',
    name: '된장찌개',
    emoji: '🥘',
    imageUrl: null,
    tags: ['따뜻한', '국물있는', '구수한', '든든한'],
    score: 85,
    reason: {
      matchedKeywords: ['따뜻한', '국물있는'],
      cfScore: 0.78,
      cfDescription: '담백한 한식을 즐기는 사용자들이 자주 선택해요',
      contextNote: '저녁 한 끼로 선호도가 높아요',
    },
  },
  {
    id: 'food-004',
    name: '갈비탕',
    emoji: '🍖',
    imageUrl: null,
    tags: ['따뜻한', '국물있는', '진한', '든든한'],
    score: 82,
    reason: {
      matchedKeywords: ['따뜻한', '국물있는'],
      cfScore: 0.74,
      cfDescription: '"든든한 국물"을 좋아하는 사용자 74%가 선택했어요',
      contextNote: '추운 날 야식·저녁으로 인기',
    },
  },
  {
    id: 'food-005',
    name: '우동',
    emoji: '🍥',
    imageUrl: null,
    tags: ['따뜻한', '국물있는', '담백한', '가벼운'],
    score: 79,
    reason: {
      matchedKeywords: ['따뜻한', '국물있는', '담백한'],
      cfScore: 0.69,
      cfDescription: '가볍게 한 끼 하려는 사용자들이 자주 함께 봐요',
      contextNote: '혼밥하기 좋은 메뉴로 분류돼요',
    },
  },
  {
    id: 'food-006',
    name: '쌀국수',
    emoji: '🍲',
    imageUrl: null,
    tags: ['따뜻한', '국물있는', '담백한', '향긋한'],
    score: 76,
    reason: {
      matchedKeywords: ['따뜻한', '국물있는', '담백한'],
      cfScore: 0.66,
      cfDescription: '"담백한 국물"을 찾는 사용자들이 새롭게 발견하는 메뉴',
      contextNote: '날씨와 무관하게 꾸준히 선호돼요',
    },
  },
];
