/**
 * keywordService.js
 *
 * 사용자의 자연어 입력 → 정형 키워드로 변환
 *
 * 현재: mock (간단한 규칙 기반 매칭)
 * 추후: Claude API (Sonnet) 연동 — 함수 시그니처는 그대로 유지
 *
 * 교수님 피드백 반영:
 *  - 키워드가 고정 리스트가 아니라 "확장 가능한 구조"
 *    → 매칭되는 키워드가 없으면 "사용자 표현 그대로" 키워드화
 *    → LLM 연결 시 사용자별로 다르게 해석된 키워드도 그대로 흘러감
 */

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
];

/**
 * 자연어 → 키워드 분석
 *
 * @param {string} text 사용자가 입력한 감성 문장
 * @returns {Promise<import('../types').AnalyzeResult>}
 */
export async function analyzeKeywords(text) {
  // === [실제 LLM 연결 시 이 부분을 fetch로 교체] ===
  //
  // const res = await fetch('https://api.anthropic.com/v1/messages', {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json', /* api key 등 */ },
  //   body: JSON.stringify({
  //     model: 'claude-sonnet-4',
  //     max_tokens: 200,
  //     messages: [
  //       { role: 'user', content: `다음 문장에서 음식 추천에 쓸 키워드 1~4개를 추출해줘: "${text}"` }
  //     ],
  //   }),
  // });
  // const data = await res.json();
  // → data.content[0].text 를 파싱해서 keywords 배열로 변환
  //
  // ===============================================

  // mock: 실제 LLM 호출 시간과 비슷하게 약 3.5초 대기
  // (LoadingOverlay 의 단계별 애니메이션 시간과 동기화)
  await delay(MOCK_ANALYZE_DURATION_MS);

  if (!text || text.trim().length === 0) {
    return { originalText: text, keywords: [] };
  }

  const lower = text.toLowerCase();
  const found = new Map(); // label → Keyword (중복 제거)

  KEYWORD_HINTS.forEach((hint) => {
    if (hint.match.some((m) => lower.includes(m))) {
      found.set(hint.label, {
        id: `kw-${slug(hint.label)}`,
        label: hint.label,
        confidence: 0.9,
        source: 'llm',
      });
    }
  });

  // 매칭이 하나도 없으면 fallback
  // (입력 자체를 그대로 키워드화 — 확장 가능 구조)
  if (found.size === 0) {
    found.set(text.trim(), {
      id: `kw-${slug(text)}-${Date.now()}`,
      label: text.trim().slice(0, 12), // 너무 길면 자름
      confidence: 0.5,
      source: 'llm',
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
