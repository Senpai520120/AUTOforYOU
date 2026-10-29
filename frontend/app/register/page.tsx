'use client';
import { trackEvent } from '@/lib/analytics';
import { useId, useState } from 'react';
import Link from 'next/link';
import { apiFetch } from '@/api/client';
import Captcha from '@/components/ui/Captcha';
import { AGE_18_LABEL, AGE_18_REQUIRED } from '@/lib/labels';
import { apiErrorText, useAuthConfig, useCaptchaState } from '@/lib/captcha';
import { getAttribution } from '@/lib/attribution';

export default function RegisterPage() {
  const { config } = useAuthConfig();
  const idPrefix = useId();
  const captcha = useCaptchaState();
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);
  const [isAdult, setIsAdult] = useState(false);
  const [form, setForm] = useState({ email: '', password: '', password2: '', first_name: '', phone: '' });
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
    if (!isAdult) {
      setError(AGE_18_REQUIRED);
      return;
    }
    setLoading(true); setError('');
    try {
      // Джерело візиту (2.14) — лише з sessionStorage; порожнє не надсилається.
      const attribution = getAttribution();
      await apiFetch('/api/v1/auth/register/', {
        method: 'POST',
        body: JSON.stringify({
          ...form, agreed_to_terms: true, confirmed_age_18: true, ...captcha.payload(),
          ...(Object.keys(attribution).length ? { attribution } : {}),
        }),
      });
      setRegisteredEmail(form.email);
      trackEvent('sign_up', { source: 'register' });
    } catch (err: unknown) {
      setError(apiErrorText(err, 'Помилка реєстрації'));
    } finally {
      setLoading(false);
      captcha.bump(); // токен одноразовий: новий після кожної відповіді сервера
    }
  };

  if (registeredEmail) {
    return (
      <div className="max-w-md mx-auto mt-10">
        <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm text-center">
          <h1 className="text-2xl font-bold text-slate-900 mb-3">Перевірте пошту</h1>
          <p className="text-slate-600 text-sm">
            Якщо адреса <strong>{registeredEmail}</strong> доступна, ми надіслали на неї лист із
            посиланням для підтвердження. Перейдіть за посиланням, щоб активувати всі функції.
          </p>
          <p className="mt-4 text-sm text-slate-500">
            <Link href="/login" className="text-blue-600 hover:underline">Перейти до входу</Link>
          </p>
        </div>
      </div>
    );
  }

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
              <label htmlFor={`${idPrefix}-${f.key}`} className="block text-sm font-semibold text-slate-700 mb-1">{f.label}</label>
              <input id={`${idPrefix}-${f.key}`} type={f.type} className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-400"
                value={form[f.key as keyof typeof form]} onChange={e => set(f.key, e.target.value)}
                required={f.key !== 'first_name' && f.key !== 'phone'} />
            </div>
          ))}
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

          <div className="flex items-start gap-3">
            <input
              id="confirmed_age_18"
              type="checkbox"
              checked={isAdult}
              onChange={e => setIsAdult(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-amber-500 focus:ring-2 focus:ring-amber-400 cursor-pointer"
              required
            />
            <label htmlFor="confirmed_age_18" className="text-sm text-slate-600 cursor-pointer leading-snug">
              {AGE_18_LABEL}
            </label>
          </div>

          <Captcha config={config?.captcha ?? null} onToken={captcha.setToken}
            resetKey={captcha.resetKey} onHoneypot={captcha.setWebsite} />

          {error && <p role="alert" className="text-red-600 text-sm">{error}</p>}
          <button type="submit" disabled={loading || !captcha.ready}
            className="w-full bg-amber-500 hover:bg-amber-400 text-black font-bold py-2.5 rounded-xl disabled:opacity-60 transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400">
            {loading ? 'Реєстрація...' : 'Зареєструватися'}
          </button>
        </form>
        <p className="mt-4 text-sm text-center text-slate-500">
          Вже є акаунт? <Link href="/login" className="text-blue-600 underline">Увійти</Link>
        </p>
      </div>
    </div>
  );
}
