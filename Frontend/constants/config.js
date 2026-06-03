/**
 * 앱 전역 설정 / 문구
 * - 화면에 보여줄 문구를 한 곳에 모아 관리하기 쉽게 함
 */

export const APP_INFO = {
  name: 'me:nu',
  tagline: '오늘의 한 끼, 기분으로 말해보세요.',
  team: '감성한입',
};

// 홈 화면 예시 문장
// 고정된 추천 멘트가 아니라 "예시"일 뿐 — 입력은 자유롭게
export const EXAMPLE_PROMPTS = [
  '칼칼하고 국물 있는 것',
  '비 오는 날 따뜻한 것',
  '기분 전환 가벼운 음식',
  '해장하기 좋은 얼큰한 국물',
  '혼자서 든든하게',
];

// 시드 14개 — Backend/src/llm/tags.py SEED_TAGS 와 동일.
// 키워드 검수 화면의 "이런 키워드는 어떠세요?" 풀로 사용 (8개씩 회전).
// LLM 추출도 이 14개 안으로 enum 잠금이라 *사용자가 고르는 것도 시드 안에서*
// 추가하면 추천에 반영 가능 (시드 외 키워드는 어차피 무시되니까).
export const SUGGESTED_KEYWORDS = [
  '따뜻한', '시원한', '얼큰한', '국물있는', '담백한',
  '진한', '가벼운', '든든한', '해장', '야식',
  '바삭한', '쫄깃한', '고소한', '달달한',
];

// API 모드 — 나중에 실제 API로 교체할 때 'real'로 바꾸기만 하면 됨
export const API_MODE = 'mock'; // 'mock' | 'real'

// 백엔드(인증 API) 주소.
// - iOS 시뮬레이터 / 웹:   http://localhost:8000
// - Android 에뮬레이터:    http://10.0.2.2:8000
// - 실제 휴대폰(Expo Go):  http://<개발PC의 LAN IP>:8000  (예: http://192.168.0.10:8000)
//   → localhost 는 폰 자신을 가리키므로 실기기에서는 반드시 PC 의 IP 로 바꿀 것.
// 백엔드 실행:  cd Backend && uvicorn auth_app:app --host 0.0.0.0 --port 8000
// /foods·/foods_cf 등 추천 API 와 /auth/* 모두 같은 호스트.
// constants/api.js 의 API_BASE 와 동일 경로로 갱신해 일관 유지.
import { API_BASE } from './api';
export const API_BASE_URL = API_BASE;
