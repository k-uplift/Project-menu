/**
 * API_BASE — 백엔드 endpoint base URL.
 *
 * Expo Go 모바일에서 호출 시 localhost는 의미 없음 — Mac의 LAN IP가 필요하다.
 * Mac과 휴대폰이 같은 Wi-Fi에 있어야 함.
 *
 * Mac IP 확인:  $ ipconfig getifaddr en0
 * Wi-Fi 바뀌면 IP도 바뀜 — 여기 한 줄만 갱신.
 *
 * 백엔드 실행:  cd Backend && uvicorn api:app --host 0.0.0.0 --port 8000
 */
export const API_BASE = 'http://192.168.219.111:8000';
