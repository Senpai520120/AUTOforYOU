'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from './auth-context';

/**
 * Клієнтський захист приватної сторінки (08-S7): гість → /login?next=<поточний шлях>.
 * Сам 401 нікуди не редиректить (api/client) — тільки сторінки, які викликають цей хук.
 */
export function useRequireAuth() {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading } = auth;

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [user, loading, router, pathname]);

  return auth;
}
