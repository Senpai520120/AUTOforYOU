'use client';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ApiError, apiPost } from '@/api/client';
import { apiErrorText } from '@/lib/captcha';

export default function PasswordResetConfirmPage() {
  // useSearchParams без Suspense ламає пререндер сторінки під час build.
  return (
    <Suspense fallback={null}>
      <ConfirmForm />
    </Suspense>
  );
}

function ConfirmForm() {
  const params = useSearchParams();
  // uid/token читаємо один раз і прибираємо з адреси: токен не лишається в історії та Referer.
  const [{ uid, token }] = useState(() => ({ uid: params.get('uid'), token: params.get('token') }));
  useEffect(() => {
    window.history.replaceState(null, '', '/password-reset/confirm');
  }, []);
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      await apiPost('/api/v1/auth/password-reset/confirm/', {
        uid, token, new_password: password, new_password2: password2,
      });
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setError('Забагато спроб. Спробуйте пізніше.');
      else setError(apiErrorText(err, 'Не вдалося змінити пароль. Спробуйте пізніше.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10">
      <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900 mb-6">Новий пароль</h1>
        {!uid || !token ? (
          <div role="alert">
            <p className="text-slate-700 text-sm mb-4">Посилання недійсне або термін його дії минув.</p>
            <Link href="/password-reset" className="text-blue-600 hover:underline text-sm">Запросити нове посилання</Link>
          </div>
        ) : done ? (
          <div role="status" data-testid="reset-done">
            <p className="text-slate-700 text-sm mb-4">Пароль змінено. Усі пристрої вийшли з акаунту — увійдіть із новим паролем.</p>
            <Link href="/login" className="text-blue-600 hover:underline text-sm">Увійти</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label htmlFor="new-password" className="block text-sm font-semibold text-slate-700 mb-1">Новий пароль</label>
              <input id="new-password" type="password" required autoComplete="new-password"
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
                value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <div>
              <label htmlFor="new-password2" className="block text-sm font-semibold text-slate-700 mb-1">Повторіть пароль</label>
              <input id="new-password2" type="password" required autoComplete="new-password"
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
                value={password2} onChange={(e) => setPassword2(e.target.value)} />
            </div>
            {error && (
              <div role="alert" data-testid="form-error" className="text-red-600 text-sm">
                <p>{error}</p>
                <Link href="/password-reset" className="text-blue-600 hover:underline">Запросити нове посилання</Link>
              </div>
            )}
            <button type="submit" disabled={loading}
              className="w-full bg-blue-700 hover:bg-blue-800 text-white font-bold py-2.5 rounded-xl disabled:opacity-60 transition-colors">
              {loading ? 'Зберігаємо...' : 'Змінити пароль'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
