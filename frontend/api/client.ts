/**
 * Клієнтські запити до API (задача 1.4).
 *
 * - Сесія — тільки httpOnly-cookie `access`/`refresh`, JS токенів не бачить і не зберігає.
 * - Небезпечні методи шлють X-CSRFToken (lib/csrf.ts).
 * - Refresh — один проміс на всі паралельні 401 у вкладці (single-flight) і Web Lock
 *   між вкладками: інакше дві вкладки шлють той самий refresh, друга отримує 401
 *   і бекенд стирає cookie, щойно поставлені першій.
 * - 401 не редиректить: кидається ApiError зі status 401 і подія `auth:expired`
 *   (AuthContext скидає user). На /login ведуть тільки захищені сторінки (useRequireAuth).
 */
import { getCsrfToken } from '@/lib/csrf';
import { hasSessionHint } from '@/lib/session-hint';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const REFRESH_PATH = '/api/v1/auth/token/refresh/';
// 401 від входу/виходу — відповідь по суті (невірний пароль, сесії вже немає), не протухший access.
const NO_REFRESH_PATHS = new Set(['/api/v1/auth/token/', REFRESH_PATH, '/api/v1/auth/token/logout/']);
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export const AUTH_EXPIRED_EVENT = 'auth:expired';
// Сесію оновлено: серверні компоненти, відрендерені з протухшим access, варто перерендерити.
export const AUTH_REFRESHED_EVENT = 'auth:refreshed';

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, data: unknown) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    super(typeof detail === 'string' ? detail : `HTTP ${status}`);
    this.status = status;
    this.data = data;
  }
}

async function send(path: string, options: RequestInit): Promise<Response> {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  // Content-Type тільки з тілом: на GET він викликав зайвий CORS-preflight (08-Q16).
  const hasJsonBody = options.body != null && !(options.body instanceof FormData);
  if (hasJsonBody && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (UNSAFE_METHODS.has(method)) {
    const csrf = await getCsrfToken();
    if (csrf) headers.set('X-CSRFToken', csrf);
  }
  return fetch(`${API}${path}`, { ...options, method, headers, credentials: 'include' });
}

// ok — сесію оновлено; expired — refresh відхилено (401), сесії немає;
// error — 429/5xx/мережа: сесія, можливо, жива, з неї не викидаємо.
type RefreshResult = 'ok' | 'expired' | 'error';

let refreshing: Promise<RefreshResult> | null = null;
// Номер «покоління» сесії: росте після кожного успішного refresh. Якщо 401 прийшов
// на запит, відправлений до останнього refresh, достатньо просто повторити запит.
let sessionEpoch = 0;

async function doRefresh(): Promise<RefreshResult> {
  try {
    const res = await send(REFRESH_PATH, { method: 'POST' });
    if (res.ok) return 'ok';
    return res.status === 401 ? 'expired' : 'error';
  } catch {
    return 'error';
  }
}

function refreshSession(): Promise<RefreshResult> {
  if (!refreshing) {
    const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
    const run = locks ? locks.request('auth-refresh', doRefresh) : doRefresh();
    refreshing = run
      .then((result) => {
        if (result === 'ok') {
          sessionEpoch += 1;
          emit(AUTH_REFRESHED_EVENT);
        }
        return result;
      })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

function emit(name: string) {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(name));
}

async function toError(res: Response): Promise<ApiError> {
  const data = await res.json().catch(() => ({}));
  return new ApiError(res.status, data);
}

async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const epoch = sessionEpoch;
  const res = await send(path, options);
  if (res.status !== 401 || NO_REFRESH_PATHS.has(path)) return res;
  if (epoch !== sessionEpoch) return send(path, options);
  // Немає мітки сесії — гість: refresh-cookie теж немає, refresh марний.
  if (!hasSessionHint()) {
    emit(AUTH_EXPIRED_EVENT);
    return res;
  }

  const result = await refreshSession();
  if (result === 'ok') return send(path, options);
  if (result === 'error') return res;
  // Refresh відхилено. Один повтор: інша вкладка могла вже оновити cookie.
  const retry = await send(path, options);
  if (retry.status === 401) emit(AUTH_EXPIRED_EVENT);
  return retry;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await request(path, options);
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function apiGet<T>(path: string) {
  return apiFetch<T>(path);
}

export function apiPost<T>(path: string, body?: unknown) {
  return apiFetch<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
}

export function apiPut<T>(path: string, body: unknown) {
  return apiFetch<T>(path, { method: 'PUT', body: JSON.stringify(body) });
}

export function apiPatch<T>(path: string, body: unknown) {
  return apiFetch<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
}

export function apiDelete(path: string) {
  return apiFetch<void>(path, { method: 'DELETE' });
}

export function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  // Content-Type з boundary браузер ставить сам — send() його не чіпає для FormData.
  return apiFetch<T>(path, { method: 'POST', body: formData });
}
