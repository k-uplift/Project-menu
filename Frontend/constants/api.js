/**
 * API_BASE — 백엔드 endpoint base URL.
 *
 * Expo Go 모바일에서 호출 시 localhost는 의미 없음 — Mac의 LAN IP가 필요하다.
 * Mac과 휴대폰이 같은 Wi-Fi에 있어야 함.
 *
 * 자동 감지:
 *   Expo dev 모드에선 React Native의 NativeModules.SourceCode.scriptURL이
 *   JS bundle URL을 노출 — 예: 'http://192.168.219.111:8081/index.bundle?...'.
 *   그 호스트가 Metro 서버 = Mac이라 백엔드도 같은 IP. 호스트만 빼서 재사용.
 *   → Wi-Fi 바뀌어도 코드 수정 불필요.
 *
 * Fallback:
 *   web 모드, prod 빌드, scriptURL 못 읽는 경우 등 → FALLBACK_HOST 사용.
 *   배포 시엔 환경변수·도메인으로 교체.
 */

import { NativeModules, Platform } from 'react-native';

const BACKEND_PORT = 8000;
// 마지막 알려진 LAN IP (수동 fallback). Wi-Fi 자주 바뀌는 환경이면 갱신.
const FALLBACK_HOST = '172.30.1.41';

function detectDevHost() {
  if (Platform.OS === 'web') return 'localhost';
  const scriptURL = NativeModules?.SourceCode?.scriptURL;
  if (!scriptURL) return null;
  // 'http://192.168.219.111:8081/index.bundle?...' → '192.168.219.111'
  const match = scriptURL.match(/^https?:\/\/([^:/]+)/);
  return match ? match[1] : null;
}

const host = detectDevHost() || FALLBACK_HOST;
export const API_BASE = `http://${host}:${BACKEND_PORT}`;

// 디버그 — 어떤 호스트로 잡혔는지 한 번만 로그
console.log(`[api] API_BASE = ${API_BASE} (detected=${detectDevHost() || 'NO'})`);
