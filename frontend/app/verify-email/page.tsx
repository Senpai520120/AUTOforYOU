'use client';
import { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { apiPost } from '@/api/client';
import { useAuth } from '@/lib/auth-context';
import { hasSessionHint } from '@/lib/session-hint';

export default function VerifyEmailPage() {
  // useSearchParams без Suspense ламає пререндер сторінки під час build.
  return (
    <Suspense fallback={null}>
      <VerifyEmail />
    </Suspense>
  );
}

function VerifyEmail() {
  const params = useSearchParams();
  const uid = params.get('uid');
  const token = params.get('token');
  const { user, refreshUser } = useAuth();
  const [state, setState] = useState<'loading' | 'ok' | 'error'>(uid && token ? 'loading' : 'error');
  // Посилання одноразове: у StrictMode (dev) ефект запускається двічі, другий запит дав би помилку.
  const sent = useRef(false);

  useEffect(() => {
    if (!uid || !token || sent.current) return;
    sent.current = true;
    apiPost('/api/v1/auth/verify-email/', { uid, token })
      .then(() => {
        setState('ok');
        // Якщо є сесія, оновити профіль (зникає банер у /me).
        if (hasSessionHint()) void refreshUser();
      })
      .catch(() => setState('error'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid, token]);

  return (
    <div className="max-w-md mx-auto mt-10">
      <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm text-center">
        {state === 'loading' && <p className="text-slate-600">Підтверджуємо email…</p>}
        {state === 'ok' && (
          <>
            <h1 className="text-2xl font-bold text-slate-900 mb-3">Email підтверджено</h1>
            <p className="text-slate-600 text-sm mb-4">Дякуємо! Тепер вам доступні всі функції сайту.</p>
            <Link href={user ? '/me' : '/login'} className="text-blue-600 hover:underline">
              {user ? 'До кабінету' : 'Увійти'}
            </Link>
          </>
        )}
        {state === 'error' && (
          <>
            <h1 className="text-2xl font-bold text-slate-900 mb-3">Не вдалося підтвердити email</h1>
            <p className="text-slate-600 text-sm mb-4">
              Посилання недійсне, прострочене або вже використане. Увійдіть і надішліть лист ще раз
              у кабінеті.
            </p>
            <Link href="/login?next=/me" className="text-blue-600 hover:underline">Увійти</Link>
          </>
        )}
      </div>
    </div>
  );
}
