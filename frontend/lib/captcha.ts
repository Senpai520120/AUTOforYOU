'use client';
/**
 * Конфігурація капчі та спільний стан форми (задача 1.6, Н-33).
 *
 * Конфіг береться з GET /api/v1/auth/config/ під час роботи, не при збірці:
 * зміна ключа Turnstile не потребує перезбірки Next.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiGet, ApiError } from '@/api/client';

export interface CaptchaConfig {
  provider: 'turnstile' | 'honeypot' | 'off';
  site_key: string;
  login_after_failures: number;
  on_login: boolean;
  /** Лише для provider=honeypot: підписаний токен форми (шлеться як captcha_token). */
  form_token?: string;
}

export interface AuthConfig {
  captcha: CaptchaConfig;
  email_verification_required: boolean;
  /** Вхід через SSO (Keycloak, задача SSO-1); старий бекенд поля не віддає → кнопки немає. */
  oidc_enabled?: boolean;
  oidc_start_url?: string | null;
}

/** config === null — ще вантажиться; error — конфіг не отримано. */
export function useAuthConfig(): { config: AuthConfig | null; error: boolean } {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    apiGet<AuthConfig>('/api/v1/auth/config/')
      .then((c) => { if (alive) setConfig(c); })
      .catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, []);
  return { config, error };
}

/**
 * Стан капчі форми. `token === null` — відправляти не можна (кнопка неактивна);
 * '' — капча вимкнена (provider=off). `bump()` викликають після КОЖНОЇ відповіді сервера.
 */
export function useCaptchaState() {
  const [token, setToken] = useState<string | null>(null);
  const [website, setWebsite] = useState('');
  const [resetKey, setResetKey] = useState(0);
  const bump = useCallback(() => setResetKey((k) => k + 1), []);
  const payload = useCallback(
    () => ({ ...(token ? { captcha_token: token } : {}), website }),
    [token, website],
  );
  return useMemo(
    () => ({ token, setToken, website, setWebsite, resetKey, bump, payload, ready: token !== null }),
    [token, website, resetKey, bump, payload],
  );
}

/** Текст помилки з відповіді API без службових полів. */
export function apiErrorText(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  const data = err.data as Record<string, unknown> | null;
  if (!data || typeof data !== 'object') return fallback;
  const parts: string[] = [];
  for (const [key, value] of Object.entries(data)) {
    if (key === 'code' || key === 'captcha_required') continue;
    if (Array.isArray(value)) parts.push(...value.map(String));
    else if (typeof value === 'string') parts.push(value);
  }
  return parts.length ? parts.join('. ') : fallback;
}

export function isCaptchaFailed(err: unknown): boolean {
  return err instanceof ApiError && (err.data as { code?: string } | null)?.code === 'captcha_failed';
}
