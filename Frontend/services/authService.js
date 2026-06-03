/**
 * authService.js — 로그인 / 회원가입 / 로그아웃
 *
 * 백엔드 엔드포인트(Backend/auth_app.py):
 *   POST /auth/signup  {email, password} → {user, token}
 *   POST /auth/login   {email, password} → {user, token}
 *   GET  /auth/me      Authorization: Bearer <token> → {user}
 *
 * 토큰과 유저 정보는 AsyncStorage 에 저장한다 → 앱을 껐다 켜도 로그인 유지.
 * 실패는 AuthError(code, message) 로 던지고, 화면은 message 를 그대로 보여주면 된다.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_BASE_URL } from '../constants/config';

const KEYS = {
  token: '@menu/auth_token',
  user: '@menu/auth_user',
};

export class AuthError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'AuthError';
    this.code = code;
  }
}

// === 내부: 백엔드 POST 호출 + 에러 정규화 ===
async function postJSON(path, body) {
  let res;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    throw new AuthError(
      'network',
      '서버에 연결할 수 없습니다. 네트워크와 API 주소(constants/config.js)를 확인해주세요.'
    );
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // 백엔드는 {detail: {code, message}} 형태로 에러를 준다
    const detail = data && data.detail;
    const code = (detail && detail.code) || `http_${res.status}`;
    const message =
      (detail && (detail.message || (typeof detail === 'string' ? detail : null))) ||
      '요청을 처리하지 못했습니다.';
    throw new AuthError(code, message);
  }
  return data;
}

async function persistSession({ user, token }) {
  await AsyncStorage.multiSet([
    [KEYS.token, token],
    [KEYS.user, JSON.stringify(user)],
  ]);
}

// === 공개 API ===

/** 회원가입 후 자동 로그인(토큰 저장). 성공 시 user 반환. */
export async function signup(email, password) {
  const data = await postJSON('/auth/signup', { email, password });
  await persistSession(data);
  return data.user;
}

/** 로그인. 성공 시 토큰 저장 후 user 반환. */
export async function login(email, password) {
  const data = await postJSON('/auth/login', { email, password });
  await persistSession(data);
  return data.user;
}

/** 로그아웃 — 저장된 토큰/유저 삭제. */
export async function logout() {
  await AsyncStorage.multiRemove([KEYS.token, KEYS.user]);
}

/** 저장된 토큰 문자열(없으면 null). */
export async function getToken() {
  return AsyncStorage.getItem(KEYS.token);
}

/** 저장된 현재 유저 객체(없으면 null). */
export async function getCurrentUser() {
  const raw = await AsyncStorage.getItem(KEYS.user);
  return raw ? JSON.parse(raw) : null;
}

/** 로그인 상태 여부. */
export async function isLoggedIn() {
  return !!(await getToken());
}

/**
 * 인증 헤더(Bearer)를 자동으로 붙이는 fetch. 추후 보호된 API 호출용.
 * 사용 예:  const res = await authFetch('/auth/me');
 */
export async function authFetch(path, options = {}) {
  const token = await getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers });
}
