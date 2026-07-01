'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { apiFetch } from '@/api/client';

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: '', password: '', password2: '', role: 'buyer', first_name: '', phone: '' });
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agreedToTerms) {
      setError('Необхідно погодитися з Умовами та Політикою конфіденційності');
      return;
    }
    setLoading(true); setError('');
    try {
      await apiFetch('/api/v1/auth/register/', {
        method: 'POST',
        body: JSON.stringify({ ...form, agreed_to_terms: true }),
      });
      router.push('/login?registered=1');
    } catch (err: unknown) {
      const e2 = err as { data?: Record<string, string[]> };
      const msgs = e2?.data ? Object.values(e2.data).flat().join('. ') : 'Помилка реєстрації';
      setError(msgs);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10">
      <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900 mb-6">Реєстрація</h1>
        <form onSubmit={submit} className="space-y-4">
          {[
            { label: "Ім'я", key: 'first_name', type: 'text' },
            { label: 'Email', key: 'email', type: 'email' },
            { label: 'Телефон', key: 'phone', type: 'tel' },
            { label: 'Пароль', key: 'password', type: 'password' },
            { label: 'Підтвердити пароль', key: 'password2', type: 'password' },
          ].map(f => (
            <div key={f.key}>
              <label className="block text-sm font-semibold text-slate-700 mb-1">{f.label}</label>
              <input type={f.type} className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-400"
                value={form[f.key as keyof typeof form]} onChange={e => set(f.key, e.target.value)}
                required={f.key !== 'first_name' && f.key !== 'phone'} />
            </div>
          ))}
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">Роль</label>
            <select className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-400"
              value={form.role} onChange={e => set('role', e.target.value)}>
              <option value="buyer">Покупець</option>
              <option value="dealer">Перекупник</option>
            </select>
          </div>

          <div className="flex items-start gap-3 pt-1">
            <input
              id="agreed_to_terms"
              type="checkbox"
              checked={agreedToTerms}
              onChange={e => setAgreedToTerms(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-amber-500 focus:ring-2 focus:ring-amber-400 cursor-pointer"
              required
            />
            <label htmlFor="agreed_to_terms" className="text-sm text-slate-600 cursor-pointer leading-snug">
              Погоджуюсь з{' '}
              <Link href="/terms" className="text-blue-600 hover:underline" target="_blank" rel="noopener">
                Умовами використання
              </Link>{' '}
              та{' '}
              <Link href="/privacy" className="text-blue-600 hover:underline" target="_blank" rel="noopener">
                Політикою конфіденційності
              </Link>
            </label>
          </div>

          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button type="submit" disabled={loading}
            className="w-full bg-amber-500 hover:bg-amber-400 text-black font-bold py-2.5 rounded-xl disabled:opacity-60 transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400">
            {loading ? 'Реєстрація...' : 'Зареєструватися'}
          </button>
        </form>
        <p className="mt-4 text-sm text-center text-slate-500">
          Вже є акаунт? <Link href="/login" className="text-blue-600 hover:underline">Увійти</Link>
        </p>
      </div>
    </div>
  );
}
