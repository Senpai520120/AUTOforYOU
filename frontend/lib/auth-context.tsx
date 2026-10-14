'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { User } from './types';
import { useRouter } from 'next/navigation';
import { ApiError, AUTH_EXPIRED_EVENT, AUTH_REFRESHED_EVENT, apiGet, apiPost } from '@/api/client';
import { hasSessionHint } from './session-hint';

interface AuthCtx {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
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

  const login = useCallback(async (email: string, password: string) => {
    try {
      await apiPost('/api/v1/auth/token/', { email, password });
    } catch (err) {
      // 429 і 5xx розрізняє задача 1.5.
      if (err instanceof ApiError && (err.status === 400 || err.status === 401)) {
        throw new Error('Невірний email або пароль');
      }
      throw new Error('Не вдалося увійти. Спробуйте пізніше.');
    }
    await fetchProfile();
  }, [fetchProfile]);

  const logout = useCallback(async () => {
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
    window.location.assign('/');
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, refreshUser: fetchProfile, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
