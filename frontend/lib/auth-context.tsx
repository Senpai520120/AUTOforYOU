'use client';

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { User, Tokens } from './types';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface AuthCtx {
  user: User | null;
  tokens: Tokens | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<string | null>;
  loading: boolean;
}

const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [tokens, setTokens] = useState<Tokens | null>(null);
  const [loading, setLoading] = useState(true);

  // Stable ref so refreshToken can call logout without circular deps
  const logoutRef = useRef<() => void>(() => {});

  const logout = useCallback(() => {
    localStorage.removeItem('access');
    localStorage.removeItem('refresh');
    setTokens(null);
    setUser(null);
  }, []);

  useEffect(() => { logoutRef.current = logout; }, [logout]);

  const fetchProfile = useCallback(async (access: string) => {
    try {
      const res = await fetch(`${API}/api/v1/auth/profile/`, {
        headers: { Authorization: `Bearer ${access}` },
      });
      if (res.ok) setUser(await res.json());
      else if (res.status === 401) logoutRef.current();
    } catch {
      // Backend unreachable — stay logged-out silently
    }
  }, []);

  const refreshToken = useCallback(async (): Promise<string | null> => {
    const stored = localStorage.getItem('refresh');
    if (!stored) return null;
    try {
      const res = await fetch(`${API}/api/v1/auth/token/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: stored }),
      });
      if (!res.ok) { logoutRef.current(); return null; }
      const data = await res.json();
      localStorage.setItem('access', data.access);
      if (data.refresh) localStorage.setItem('refresh', data.refresh);
      setTokens(t => t ? { ...t, access: data.access } : { access: data.access, refresh: stored });
      return data.access;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    const access = localStorage.getItem('access');
    const refresh = localStorage.getItem('refresh');
    if (access && refresh) {
      setTokens({ access, refresh });
      fetchProfile(access).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [fetchProfile]);

  const login = async (email: string, password: string) => {
    const res = await fetch(`${API}/api/v1/auth/token/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error('Невірний email або пароль');
    const data: Tokens = await res.json();
    localStorage.setItem('access', data.access);
    localStorage.setItem('refresh', data.refresh);
    setTokens(data);
    await fetchProfile(data.access);
  };

  return (
    <AuthContext.Provider value={{ user, tokens, login, logout, refreshToken, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
