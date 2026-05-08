/**
 * 음식점 mock 데이터 (한성대 기숙사 기준 위치 반영)
 *
 * 한성대 기숙사 좌표: 37.582656, 127.010369
 *
 * 각 음식점에 latitude/longitude 추가 → 거리 자동 계산 가능
 * (기존의 distanceKm/walkMin 은 fallback 용으로 유지)
 *
 * 음식점들은 한성대 주변(혜화/성신여대/안암/창신동) 거리감 반영
 */

export const MOCK_RESTAURANTS_BY_FOOD = {
  // 순두부찌개 - 한성대 주변
  'food-001': [
    {
      id: 'rest-001',
      name: '한성순두부집',
      latitude: 37.583500,
      longitude: 127.011200,
      rating: 4.7,
      reviewCount: 342,
      priceRange: '8,000~15,000원',
      delivery: true,
      address: '서울 성북구 삼선동2가 245-3',
      category: '한식 · 찌개 전골',
      cfMatch: 0.92,
      hours: '11:00 ~ 21:30',
      closedDay: '일요일',
      signature: '얼큰순두부',
      menuItems: [
        { name: '얼큰순두부', price: 8000, isSignature: true },
        { name: '해물순두부', price: 10000, isSignature: true },
        { name: '뚝배기불고기', price: 12000, isSignature: false },
        { name: '제육볶음', price: 11000, isSignature: false },
      ],
    },
    {
      id: 'rest-002',
      name: '북창동순두부 혜화점',
      latitude: 37.581200,
      longitude: 127.013500,
      rating: 4.5,
      reviewCount: 528,
      priceRange: '9,000~14,000원',
      delivery: true,
      address: '서울 종로구 명륜2가 8-1',
      category: '한식 · 찌개 전골',
      cfMatch: 0.81,
      hours: '10:30 ~ 22:00',
      closedDay: '연중무휴',
      signature: '얼큰순두부',
      menuItems: [
        { name: '얼큰순두부', price: 9000, isSignature: true },
        { name: '버섯순두부', price: 9500, isSignature: false },
        { name: '굴순두부', price: 11000, isSignature: false },
        { name: '갈비탕', price: 14000, isSignature: false },
      ],
    },
    {
      id: 'rest-003',
      name: '할머니순두부집',
      latitude: 37.585800,
      longitude: 127.008100,
      rating: 4.8,
      reviewCount: 189,
      priceRange: '7,000~12,000원',
      delivery: false,
      address: '서울 성북구 삼선동5가 13-5',
      category: '한식 · 찌개 전골',
      cfMatch: 0.74,
      hours: '11:30 ~ 20:00',
      closedDay: '월요일',
      signature: '담백순두부',
      menuItems: [
        { name: '얼큰순두부찌개', price: 7500, isSignature: true },
        { name: '담백순두부찌개', price: 7500, isSignature: true },
        { name: '청국장', price: 8000, isSignature: false },
        { name: '된장찌개', price: 7000, isSignature: false },
      ],
    },
  ],
  // 칼국수 - 한성대 주변
  'food-002': [
    {
      id: 'rest-101',
      name: '삼선교 손칼국수',
      latitude: 37.583000,
      longitude: 127.011900,
      rating: 4.4,
      reviewCount: 412,
      priceRange: '8,000~14,000원',
      delivery: true,
      address: '서울 성북구 삼선동1가 304',
      category: '한식 · 면 요리',
      cfMatch: 0.85,
      hours: '11:00 ~ 21:00',
      closedDay: '일요일',
      signature: '바지락칼국수',
      menuItems: [
        { name: '바지락칼국수', price: 9000, isSignature: true },
        { name: '들깨칼국수', price: 9500, isSignature: true },
        { name: '얼큰칼국수', price: 9000, isSignature: false },
        { name: '왕만두', price: 8000, isSignature: false },
      ],
    },
    {
      id: 'rest-102',
      name: '명동칼국수 성북점',
      latitude: 37.586500,
      longitude: 127.014800,
      rating: 4.3,
      reviewCount: 230,
      priceRange: '8,000~12,000원',
      delivery: true,
      address: '서울 성북구 동소문동',
      category: '한식 · 면 요리',
      cfMatch: 0.72,
      hours: '10:30 ~ 21:30',
      closedDay: '연중무휴',
      signature: '사골칼국수',
      menuItems: [
        { name: '사골칼국수', price: 8500, isSignature: true },
        { name: '얼큰칼국수', price: 9000, isSignature: false },
        { name: '비빔국수', price: 8000, isSignature: false },
      ],
    },
  ],
};

/**
 * 음식 ID별 음식점이 없을 때 사용할 기본 데이터
 * (한성대 인근 가상 음식점)
 */
export const DEFAULT_RESTAURANTS = [
  {
    id: 'rest-default-1',
    name: '동네 맛집',
    latitude: 37.584000,
    longitude: 127.011500,
    rating: 4.5,
    reviewCount: 156,
    priceRange: '9,000~14,000원',
    delivery: true,
    address: '서울 성북구 삼선동',
    category: '한식',
    cfMatch: 0.7,
    hours: '11:00 ~ 21:00',
    closedDay: '연중무휴',
    signature: '대표메뉴',
    menuItems: [
      { name: '대표 메뉴', price: 9000, isSignature: true },
      { name: '추가 메뉴', price: 11000, isSignature: false },
      { name: '디저트', price: 5000, isSignature: false },
    ],
  },
  {
    id: 'rest-default-2',
    name: '근처 식당',
    latitude: 37.580500,
    longitude: 127.013200,
    rating: 4.2,
    reviewCount: 89,
    priceRange: '8,000~13,000원',
    delivery: false,
    address: '서울 성북구 삼선동',
    category: '한식',
    cfMatch: 0.65,
    hours: '11:30 ~ 20:30',
    closedDay: '화요일',
    signature: '오늘의 메뉴',
    menuItems: [
      { name: '오늘의 메뉴', price: 8500, isSignature: true },
      { name: '추가 메뉴', price: 10000, isSignature: false },
    ],
  },
];
