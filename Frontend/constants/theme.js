/**
 * 디자인 토큰 (Design Tokens)
 * - 데모의 따뜻한 다크 테마(주황색 액센트)를 그대로 유지
 * - 색상/간격/폰트를 한 곳에서 관리해 일관성 확보
 */

export const COLORS = {
  // 배경 (다크)
  bg: '#0E0B0A',          // 가장 어두운 배경
  surface: '#1A1513',     // 카드/입력창 배경
  surfaceAlt: '#241D1A',  // 살짝 밝은 표면 (호버/선택)
  border: '#2E2622',      // 구분선

  // 텍스트
  textPrimary: '#FFF7F0',
  textSecondary: '#C9BBB1',
  textMuted: '#8A7C72',

  // 브랜드 (따뜻한 주황)
  primary: '#FF7A33',
  primaryDim: '#C75A1F',
  primarySoft: 'rgba(255, 122, 51, 0.14)',

  // 보조
  accent: '#FFB266',      // 강조 텍스트/배지
  success: '#4ADE80',
  warning: '#FACC15',
  danger: '#F87171',

  // 점수 차트
  scoreHigh: '#FF7A33',
  scoreMid: '#FFB266',
  scoreLow: '#8A7C72',
};

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
};

export const RADIUS = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  pill: 999,
};

export const FONT = {
  sizeXs: 12,
  sizeSm: 13,
  sizeBase: 15,
  sizeMd: 17,
  sizeLg: 20,
  sizeXl: 24,
  sizeXxl: 30,

  weightRegular: '400',
  weightMedium: '500',
  weightBold: '700',
  weightExtra: '800',
};

export const SHADOW = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 12,
    elevation: 4,
  },
  primary: {
    shadowColor: COLORS.primary,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 14,
    elevation: 6,
  },
};
