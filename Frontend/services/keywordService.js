/**
 * keywordService.js
 *
 * 사용자의 자연어 입력 → 정형 키워드로 변환
 *
 * 메인: 백엔드 /extract 호출 (Claude Sonnet 4.6 + 시드 14 enum + food_keywords)
 *   → 시드 14 안에서 매핑된 *진짜 의미 키워드*. "고기·면·회" 같은 카테고리도
 *     food_keywords 채널로 함께 노출.
 *
 * Fallback: 백엔드 호출 실패 시 *프론트 규칙 매칭*으로 임시 동작.
 *   매칭 0이면 입력 자체를 키워드화 (확장 가능 구조 유지).
 */

import { API_BASE } from '../constants/api';

// LoadingOverlay의 총 분석 시간과 동기화
// (LoadingOverlay.js 의 ANALYSIS_STEPS 합계와 일치)
const MOCK_ANALYZE_DURATION_MS = 3500;

// 단순 매칭용 사전 — 데모 시연을 위한 mock 데이터일 뿐,
// 실제 서비스에서는 LLM이 동적으로 키워드를 생성한다
const KEYWORD_HINTS = [
  { match: ['따뜻', '뜨거', '뜨끈'], label: '따뜻한' },
  { match: ['시원', '차가', '얼음'], label: '시원한' },
  { match: ['칼칼', '얼큰', '매운', '맵'], label: '얼큰한' },
  { match: ['국물', '찌개', '탕'], label: '국물있는' },
  { match: ['담백', '깔끔'], label: '담백한' },
  { match: ['진한', '깊은', '구수'], label: '진한' },
  { match: ['가벼', '간단', '간편'], label: '가벼운' },
  { match: ['든든', '배부르', '푸짐'], label: '든든한' },
  { match: ['해장'], label: '해장' },
  { match: ['야식'], label: '야식' },
  { match: ['바삭'], label: '바삭한' },
  { match: ['쫄깃'], label: '쫄깃한' },
  { match: ['고소', '치즈', '크림', '버터'], label: '고소한' },
  { match: ['달달', '달콤', '단짠', '꿀', '시럽', '디저트'], label: '달달한' },
];

/**
 * 자연어 → 키워드 분석. 백엔드 /extract 호출 (Claude). 실패 시 mock fallback.
 *
 * @param {string} text 사용자가 입력한 감성 문장
 * @returns {Promise<import('../types').AnalyzeResult>}
 */
export async function analyzeKeywords(text) {
  if (!text || text.trim().length === 0) {
    return { originalText: text, keywords: [] };
  }

  try {
    const url = `${API_BASE}/extract?q=${encodeURIComponent(text.trim())}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // 백엔드가 이미 프론트 Keyword 구조로 변환해서 보냄.
    // foodKeywords 는 *내부 매칭 보조 채널* — UI 에 노출 X, 추천 호출 시 같이 흘려보냄.
    return {
      originalText: data.originalText || text,
      keywords: Array.isArray(data.keywords) ? data.keywords : [],
      foodKeywords: Array.isArray(data.foodKeywords) ? data.foodKeywords : [],
    };
  } catch (e) {
    console.warn('[keywordService] /extract 실패 → mock fallback:', e.message);
    return analyzeKeywordsMock(text);
  }
}

/**
 * Mock fallback — 백엔드 다운 시 임시 동작. 시드 14개 부분문자열 매칭.
 */
async function analyzeKeywordsMock(text) {
  // 실제 호출과 비슷한 대기 시간
  await delay(MOCK_ANALYZE_DURATION_MS);

  const lower = text.toLowerCase();
  const found = new Map();

  KEYWORD_HINTS.forEach((hint) => {
    if (hint.match.some((m) => lower.includes(m))) {
      found.set(hint.label, {
        id: `kw-${slug(hint.label)}`,
        label: hint.label,
        confidence: 0.9,
        source: 'mock',
      });
    }
  });

  // 매칭이 하나도 없으면 입력 자체를 키워드화 (확장 가능 구조)
  if (found.size === 0) {
    found.set(text.trim(), {
      id: `kw-${slug(text)}-${Date.now()}`,
      label: text.trim().slice(0, 12),
      confidence: 0.5,
      source: 'mock',
    });
  }

  return {
    originalText: text,
    keywords: Array.from(found.values()),
  };
}

/**
 * 사용자가 직접 키워드를 추가할 때 호출
 * (LLM 호출 없이 즉시 Keyword 객체로 변환)
 *
 * @param {string} label
 * @returns {import('../types').Keyword}
 */
export function createUserKeyword(label) {
  const trimmed = label.trim();
  return {
    id: `kw-user-${slug(trimmed)}-${Date.now()}`,
    label: trimmed,
    confidence: 1.0,       // 사용자가 직접 입력 → 신뢰도 1
    source: 'user',
  };
}

// --- 내부 유틸 ---
function slug(s) {
  return s.replace(/\s+/g, '-').slice(0, 20);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
