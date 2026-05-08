# me:nu — 감성 기반 음식 추천 앱

> 사용자의 감성 표현을 LLM이 분석해 키워드 → 음식 → 음식점까지 추천하는 React Native (Expo) 앱

빅데이터캡스톤디자인 · 팀 감성한입 · 한성대학교 · 2026

---

##  실행 방법

```bash
npm install
npx expo start
```

Expo Go 앱으로 QR을 스캔하거나, `i` (iOS) / `a` (Android) 키로 실행.

---

##  프로젝트 구조

```
menu-app/ 
├── App.js                       # 진입점 + 네비게이션 (Home → Keyword → Recommend → Restaurant)
│
├── screens/                     # 화면 단위 컴포넌트
│   ├── HomeScreen.js            # STEP 1: 자연어 입력
│   ├── KeywordScreen.js         # STEP 2: 키워드 확인/수정/추가
│   ├── RecommendScreen.js       # STEP 3: 음식 추천 (기본 vs CF 탭)
│   └── RestaurantScreen.js      # STEP 4: 음식점 추천 + 외부 연결
│
├── components/                  # 재사용 컴포넌트
│   ├── ScreenContainer.js       # 모든 화면 공통 레이아웃
│   ├── StepIndicator.js         # 상단 단계 표시 (4단계)
│   ├── PrimaryButton.js         # 메인 액션 버튼
│   ├── KeywordTag.js            # 키워드 칩
│   ├── FoodCard.js              # 음식 추천 카드 (CF 이유 포함)
│   ├── RestaurantCard.js        # 음식점 카드
│   └── LoadingOverlay.js        # 분석 중 로딩 화면
│
├── services/                    # API 연결 진입점 (mock → real)
│   ├── keywordService.js        # analyzeKeywords(text)         → LLM 연결 예정
│   ├── recommendationService.js # getFoodRecommendations(...)   → CF 엔진 연결 예정
│   └── restaurantService.js     # getRestaurantsByFood(foodId)  → DB/Map API 연결 예정
│
├── data/                        # mock 데이터 (실제 서비스에서는 백엔드)
│   ├── foods.mock.js
│   └── restaurants.mock.js
│
├── types/                       # 데이터 타입 정의 (JSDoc)
│   └── index.js
│
└── constants/                   # 디자인 토큰 + 설정
    ├── theme.js                 # 색상/간격/타이포그래피
    └── config.js                # 앱 정보 + 예시 문장
```

---

## 교수님 피드백 반영

### 1. 핵심 흐름이 명확하게 보이도록
- 모든 화면 상단에 **StepIndicator** (4단계 진행 표시) 노출
- Stack Navigator로 단방향 흐름 구성: 입력 → 키워드 → 음식 → 음식점

### 2. CF의 역할이 추천 이유에 드러나도록
- `FoodCard` 컴포넌트의 추천 이유를 **3종으로 명시 분리**:
  1.  **감성 매칭** — 어떤 키워드가 일치했는지
  2.  **유사 사용자** — 협업 필터링 결과 (강조 표시)
  3.  **지금 상황** — 컨텍스트 (날씨/시간)
- `RecommendScreen` 에 **"기본 추천 vs 나를 위한 추천(CF)" 탭** 으로 비교 가능
- `RestaurantScreen` 에 거리순 vs 취향 맞춤(CF) 정렬 + CF 일치도 시각화

### 3. 감성 표현이 사용자마다 다르게 해석되는 점
- AI 추출 키워드를 **사용자가 직접 검수/수정/추가** 할 수 있음 (KeywordScreen)
- 입력 원문을 항상 함께 표시 → "어떤 표현에서 이 키워드가 나왔는지" 명시
- "이 키워드가 맞나요?" UX 적용

### 4. 키워드 생성이 확장 가능한 구조
- `keywordService.js` 에서 매칭 사전이 비어도 **사용자 입력을 그대로 키워드화** (fallback)
- 키워드 객체에 `source: 'llm' | 'user'` 플래그 → 출처 추적 가능
- 추천 키워드 풀(`SUGGESTED_KEYWORDS`)은 단순 UI 도우미일 뿐, 추천 로직과 분리

---

## 🔌 API 연결 가이드 (mock → real)

services 폴더의 함수는 **시그니처만 유지**하고 내부만 교체하면 됩니다.

### 1. LLM 연결 — `services/keywordService.js`

```js
export async function analyzeKeywords(text) {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': API_KEY },
    body: JSON.stringify({
      model: 'claude-sonnet-4',
      max_tokens: 200,
      messages: [{ role: 'user', content: PROMPT_TEMPLATE + text }],
    }),
  });
  const data = await res.json();
  return parseClaudeResponse(data); // Keyword[] 반환
}
```

### 2. CF 추천 엔진 — `services/recommendationService.js`

```js
export async function getFoodRecommendations(keywords, context) {
  const res = await fetch('https://api.menu-app.com/recommend', {
    method: 'POST',
    body: JSON.stringify({ keywords, context }),
  });
  return await res.json(); // FoodItem[] 반환
}
```

### 3. 음식점 DB — `services/restaurantService.js`

```js
export async function getRestaurantsByFood(foodId, { sort }) {
  const res = await fetch(
    `https://api.menu-app.com/restaurants?food=${foodId}&sort=${sort}`
  );
  return await res.json(); // Restaurant[] 반환
}
```

화면 코드는 **하나도 바꿀 필요가 없습니다.**

---

## 디자인 시스템

데모의 따뜻한 다크 테마(주황 액센트)를 그대로 유지하면서, 모든 색상/간격/폰트를 `constants/theme.js` 에서 토큰으로 관리합니다.

| 항목 | 토큰 | 값 |
|---|---|---|
| 배경 | `COLORS.bg` | `#0E0B0A` |
| 표면 | `COLORS.surface` | `#1A1513` |
| 브랜드 | `COLORS.primary` | `#FF7A33` |
| 둥근 모서리 | `RADIUS.lg` | `16px` |

---

##  발표 시연 시나리오 (추천)

1. **입력**: "비 오는 날 혼자 먹을 따뜻한 것" 타이핑
2. **키워드**: AI가 추출한 `#따뜻한 #국물있는` 등을 보여주고, 한두 개 토글하거나 추가
3. **음식**: 기본 추천 탭에서 일치도 확인 → **나를 위한 추천(CF) 탭으로 전환**
   - "비슷한 취향의 사용자 91%가 비 오는 저녁에 이 메뉴를 선택했어요" 강조
4. **음식점**: 거리순 → 취份 맞춤(CF) 전환 시 **CF 매칭도 바**가 보이는 점 강조
5. **외부 연결**: 배민/요기요/카카오맵/네이버 버튼으로 자연스럽게 마무리
