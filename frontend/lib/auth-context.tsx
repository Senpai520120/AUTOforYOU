'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { User } from './types';
import { useRouter } from 'next/navigation';
import { ApiError, AUTH_EXPIRED_EVENT, AUTH_REFRESHED_EVENT, apiGet, apiPost } from '@/api/client';
import { hasSessionHint, hasSsoHint } from './session-hint';

/** Помилка входу; captchaRequired — сервер вимагає капчу (після N невдач або CAPTCHA_ON_LOGIN). */
export class LoginError extends Error {
  captchaRequired: boolean;
  constructor(message: string, captchaRequired = false) {
    super(message);
    this.captchaRequired = captchaRequired;
  }
}

export interface LoginCaptcha {
  captcha_token?: string;
  website?: string;
}

interface AuthCtx {
  user: User | null;
  login: (email: string, password: string, captcha?: LoginCaptcha) => Promise<void>;
  logout: () => Promise<void>;
  /** Завершує всі сесії (усі пристрої) і веде на /login; кидає помилку, якщо сервер не відповів. */
  logoutAll: () => Promise<void>;
  refreshUser: () => Promise<void>;
  loading: boolean;
}

const AuthContext = createContext<AuthCtx | null>(null);

const PROFILE_PATH = '/api/v1/auth/profile/';

/**
 * До задачі 1.4 токени лежали в localStorage; refresh живе 7 днів і досі приймається
 * з тіла запиту. Прибираємо їх з досяжності JS у тих, хто входив до оновлення.
 */
function purgeLegacyTokens() {
  try {
    window.localStorage.removeItem('access');
    window.localStorage.removeItem('refresh');
  } catch {
    // localStorage недоступний (приватний режим) — прибирати нічого.
  }
}

/**
 * Сесія — httpOnly-cookie (задача 1.4): стан входу дізнаємось лише з відповіді
 * GET /auth/profile/. 200 → user, 401 (після спроби refresh у api/client) → гість.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = useCallback(async () => {
    try {
      setUser(await apiGet<User>(PROFILE_PATH));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setUser(null);
      // Бекенд недоступний — стан не чіпаємо, щоб не «виходити» через збій мережі.
    }
  }, []);

  useEffect(() => {
    purgeLegacyTokens();
    // Без мітки сесії гість: profile дав би лише 401 (і запит під анонімний ліміт).
    const init = hasSessionHint() ? fetchProfile() : Promise.resolve();
    init.finally(() => setLoading(false));
  }, [fetchProfile]);

  const router = useRouter();
  useEffect(() => {
    const onExpired = () => setUser(null);
    // SSR не бачить refresh-cookie: після оновлення сесії на клієнті перерендерити
    // серверні компоненти з новим access (lib/server-api.ts, serverGetAuthed).
    const onRefreshed = () => router.refresh();
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    window.addEventListener(AUTH_REFRESHED_EVENT, onRefreshed);
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
      window.removeEventListener(AUTH_REFRESHED_EVENT, onRefreshed);
    };
  }, [router]);

  const login = useCallback(async (email: string, password: string, captcha?: LoginCaptcha) => {
    try {
      await apiPost('/api/v1/auth/token/', { email, password, ...captcha });
    } catch (err) {
      const body = err instanceof ApiError ? (err.data as { code?: string; captcha_required?: boolean } | null) : null;
      if (err instanceof ApiError && err.status === 400 && body?.code === 'captcha_failed') {
        throw new LoginError('Перевірку не пройдено. Спробуйте ще раз.', true);
      }
      if (err instanceof ApiError && err.status === 401 && body?.captcha_required) {
        throw new LoginError('Невірний email або пароль', true);
      }
      if (err instanceof ApiError && err.status === 429) {
        const sec = Number((err.data as { retry_after?: unknown } | null)?.retry_after);
        const min = Number.isFinite(sec) && sec > 0 ? Math.ceil(sec / 60) : null;
        throw new Error(
          min ? `Забагато спроб. Спробуйте через ${min} хв.` : 'Забагато спроб. Спробуйте пізніше.',
        );
      }
      if (err instanceof ApiError && (err.status === 400 || err.status === 401)) {
        throw new Error('Невірний email або пароль');
      }
      throw new Error('Сервіс тимчасово недоступний');
    }
    await fetchProfile();
  }, [fetchProfile]);

  const logout = useCallback(async () => {
    // Читаємо до запиту: сервер видаляє мітку разом з cookie сесії.
    const viaSso = hasSsoHint();
    try {
      // Сервер відкликає refresh і видаляє обидві cookie (08-S2).
      await apiPost('/api/v1/auth/token/logout/');
    } catch (err) {
      // 400 — «сесію вже завершено», cookie сервер теж видалив. Решта (мережа, 403 CSRF,
      // 5xx): cookie лишилися — не вдаємо вихід, інакше на спільному комп'ютері сесія жива.
      if (!(err instanceof ApiError && err.status === 400)) {
        window.alert('Не вдалося вийти. Перевірте з’єднання і спробуйте ще раз.');
        return;
      }
    }
    // Повне перезавантаження на головну: з пам'яті вкладки зникають особисті дані,
    // а захищена сторінка не встигає перекинути на /login?next=… (08-S2).
    // Вхід через SSO: ще й завершити сесію Keycloak (він поверне на головну).
    window.location.assign(viaSso ? '/api/v1/auth/oidc/logout/' : '/');
  }, []);

  const logoutAll = useCallback(async () => {
    await apiPost('/api/v1/auth/token/logout-all/'); // помилка йде до викликача: cookie лишилися
    setUser(null);
    window.location.assign('/login');
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, logoutAll, refreshUser: fetchProfile, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
