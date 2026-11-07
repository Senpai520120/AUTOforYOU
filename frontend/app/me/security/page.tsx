'use client';
import { useState } from 'react';
import Link from 'next/link';
import { ApiError, apiPost } from '@/api/client';
import { useRequireAuth } from '@/lib/use-require-auth';
import { apiErrorText } from '@/lib/captcha';

export default function SecurityPage() {
  const { user, loading, logoutAll } = useRequireAuth();
  const [oldPassword, setOldPassword] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [saving, setSaving] = useState(false);
  const [allError, setAllError] = useState('');

  if (loading || !user) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError(''); setDone(false);
    try {
      await apiPost('/api/v1/auth/password-change/', {
        old_password: oldPassword, new_password: password, new_password2: password2,
      });
      setDone(true);
      setOldPassword(''); setPassword(''); setPassword2('');
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setError('Забагато спроб. Спробуйте пізніше.');
      else setError(apiErrorText(err, 'Не вдалося змінити пароль. Спробуйте пізніше.'));
    } finally {
      setSaving(false);
    }
  };

  const exitAll = async () => {
    setAllError('');
    try {
      await logoutAll();
    } catch {
      setAllError('Не вдалося вийти на всіх пристроях. Спробуйте ще раз.');
    }
  };

  const input = 'w-full border border-slate-300 rounded-lg px-3 py-2';
  return (
    <div className="max-w-2xl mx-auto">
      <Link href="/me" className="text-sm text-blue-600 hover:underline">← До кабінету</Link>
      <h1 className="text-2xl font-bold text-slate-900 mt-2 mb-6">Безпека</h1>

      <section className="bg-white border border-slate-200 rounded-2xl p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Зміна пароля</h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="old-password" className="block text-sm font-semibold text-slate-700 mb-1">Поточний пароль</label>
            <input id="old-password" type="password" required autoComplete="current-password" className={input}
              value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} />
          </div>
          <div>
            <label htmlFor="new-password" className="block text-sm font-semibold text-slate-700 mb-1">Новий пароль</label>
            <input id="new-password" type="password" required autoComplete="new-password" className={input}
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div>
            <label htmlFor="new-password2" className="block text-sm font-semibold text-slate-700 mb-1">Повторіть новий пароль</label>
            <input id="new-password2" type="password" required autoComplete="new-password" className={input}
              value={password2} onChange={(e) => setPassword2(e.target.value)} />
          </div>
          {error && <p role="alert" data-testid="form-error" className="text-red-600 text-sm">{error}</p>}
          {done && (
            <p role="status" className="text-green-700 text-sm">Пароль змінено, інші пристрої вийшли з акаунту</p>
          )}
          <button type="submit" disabled={saving}
            className="bg-blue-700 hover:bg-blue-800 text-white font-bold px-5 py-2.5 rounded-xl disabled:opacity-60 transition-colors">
            {saving ? 'Зберігаємо...' : 'Змінити пароль'}
          </button>
        </form>
      </section>

      <section className="bg-white border border-slate-200 rounded-2xl p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-2">Сесії</h2>
        <p className="text-sm text-slate-500 mb-4">Завершить усі сесії, зокрема на цьому пристрої. Знадобиться увійти знову.</p>
        {allError && <p role="alert" className="text-red-600 text-sm mb-2">{allError}</p>}
        <button type="button" onClick={exitAll}
          className="border border-slate-300 hover:border-red-300 hover:text-red-600 text-slate-700 px-5 py-2 rounded-xl text-sm transition-colors">
          Вийти на всіх пристроях
        </button>
      </section>
    </div>
  );
}
