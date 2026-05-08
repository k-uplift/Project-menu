/**
 * contextService.js
 *
 * 사용자 환경 컨텍스트 자동 감지
 *  - 현재 시간대 (아침/점심/저녁/야식)
 *  - 현재 날씨 (맑음/흐림/비/눈)
 *  - 현재 위치 (한성대 기숙사 기준)
 *
 * 현재: mock (시간은 실제 시간 사용, 날씨/위치는 더미)
 * 추후: 날씨 API + GPS 연결 — 함수 시그니처 그대로 유지
 */

// 한성대학교 기숙사 좌표 (기준점)
export const BASE_LOCATION = {
  name: '한성대 기숙사',
  latitude: 37.582656,
  longitude: 127.010369,
  address: '서울 성북구 삼선동',
};

/**
 * 현재 시간대 분류
 * @returns {{ key: string, label: string, hour: number }}
 */
export function getCurrentTimeContext() {
  const now = new Date();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const timeStr = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;

  let key, label;
  if (hour >= 5 && hour < 11) {
    key = 'morning';
    label = '아침';
  } else if (hour >= 11 && hour < 14) {
    key = 'lunch';
    label = '점심';
  } else if (hour >= 14 && hour < 17) {
    key = 'afternoon';
    label = '오후';
  } else if (hour >= 17 && hour < 21) {
    key = 'dinner';
    label = '저녁';
  } else {
    key = 'late';
    label = '야식';
  }

  return { key, label, hour, timeStr, displayText: `${label} · ${timeStr}` };
}

/**
 * 현재 날씨 가져오기
 *
 * @returns {Promise<{ key: string, label: string, emoji: string, displayText: string }>}
 */
export async function getCurrentWeather() {
  // === [실제 날씨 API 연결 시 이 부분 교체] ===
  //
  // const res = await fetch(
  //   `https://api.openweathermap.org/data/2.5/weather?lat=${lat}&lon=${lon}&appid=${KEY}&lang=kr`
  // );
  // const data = await res.json();
  // → data.weather[0].main 을 분류해서 반환
  //
  // 또는 기상청 API:
  // https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst
  // ============================================

  await delay(200);

  // mock: 현재 시간을 시드로 살짝 변동 (시연 시 다양한 결과)
  const conditions = [
    { key: 'cloudy', label: '흐림', emoji: '☁️' },
    { key: 'rain', label: '비', emoji: '🌧️' },
    { key: 'clear', label: '맑음', emoji: '☀️' },
  ];

  // 데모용: 현재 시간(분)을 3으로 나눈 나머지로 결정
  // → 발표 시 어느 시간이든 다양한 결과 노출
  const idx = new Date().getMinutes() % 3;
  const condition = conditions[idx];

  return {
    ...condition,
    displayText: `${condition.label} · 서울`,
  };
}

/**
 * 두 좌표 간 직선 거리 계산 (km)
 * Haversine formula
 */
export function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371; // 지구 반지름 (km)
  const toRad = (deg) => (deg * Math.PI) / 180;

  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) *
      Math.cos(toRad(lat2)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * 도보 시간 추정 (km → 분)
 * 평균 도보 속도 4 km/h 기준
 */
export function walkMinutesFromKm(km) {
  return Math.max(1, Math.round((km / 4) * 60));
}

/**
 * 시간대별 추천 이유 문구 생성
 */
export function getTimeBasedReason(timeKey) {
  const messages = {
    morning: '아침 시간대 인기 메뉴예요',
    lunch: '점심에 자주 선택돼요',
    afternoon: '오후 한 끼로 좋아요',
    dinner: '저녁 시간대 선호도가 높아요',
    late: '야식 메뉴로 인기예요',
  };
  return messages[timeKey] || '지금 시간대에 잘 어울려요';
}

/**
 * 날씨 기반 추천 이유 문구 생성
 */
export function getWeatherBasedReason(weatherKey) {
  const messages = {
    rain: '비 오는 날에 선호도가 높아요',
    cloudy: '흐린 날 따뜻하게 한 끼 하기 좋아요',
    clear: '맑은 날 가볍게 즐기기 좋아요',
    snow: '눈 오는 날 따뜻한 음식이에요',
  };
  return messages[weatherKey] || '오늘 날씨에 잘 어울려요';
}

/**
 * 시간 + 날씨를 조합한 추천 이유
 * 예: "비 오는 저녁 시간대 선호도가 높아요"
 */
export function getCombinedContextReason(timeCtx, weatherCtx) {
  const timePart = {
    morning: '아침',
    lunch: '점심',
    afternoon: '오후',
    dinner: '저녁',
    late: '야식',
  }[timeCtx.key] || '지금';

  const weatherPart = {
    rain: '비 오는',
    cloudy: '흐린 날',
    clear: '맑은 날',
    snow: '눈 오는',
  }[weatherCtx.key] || '';

  if (weatherPart) {
    return `${weatherPart} ${timePart} 시간대 선호도가 높아요`;
  }
  return `${timePart} 시간대에 자주 선택돼요`;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
