'use client';
import { Suspense, useState } from 'react';
import { LoginError, useAuth } from '@/lib/auth-context';
import Captcha from '@/components/ui/Captcha';
import { useAuthConfig, useCaptchaState } from '@/lib/captcha';
import { safeNext } from '@/lib/safe-next';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';

export default function LoginPage() {
  // useSearchParams без Suspense ламає пререндер сторінки під час build.
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  // Повернення тільки на шлях цього сайту (08-S7, 10-S7).
  const next = safeNext(useSearchParams().get('next'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { config } = useAuthConfig();
  const captcha = useCaptchaState();
  // Капча: одразу при CAPTCHA_ON_LOGIN, інакше після відповіді сервера captcha_required.
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const showCaptcha = !!config && (config.captcha.on_login || captchaRequired) && config.captcha.provider !== 'off';

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      await login(email, password, showCaptcha ? captcha.payload() : undefined);
      router.replace(next);
    } catch (err: unknown) {
      if (err instanceof LoginError && err.captchaRequired) setCaptchaRequired(true);
      setError((err as Error).message);
    } finally {
      setLoading(false);
      if (showCaptcha || captchaRequired) captcha.bump(); // токен одноразовий
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10">
      <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900 mb-6">Вхід</h1>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">Email</label>
            <input type="email" required className="w-full border border-slate-300 rounded-lg px-3 py-2"
              value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">Пароль</label>
            <input type="password" required className="w-full border border-slate-300 rounded-lg px-3 py-2"
              value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          {showCaptcha && (
            <Captcha config={config?.captcha ?? null} onToken={captcha.setToken}
              resetKey={captcha.resetKey} onHoneypot={captcha.setWebsite} />
          )}
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button type="submit" disabled={loading || (showCaptcha && !captcha.ready)}
            className="w-full bg-blue-700 hover:bg-blue-800 text-white font-bold py-2.5 rounded-xl disabled:opacity-60 transition-colors">
            {loading ? 'Вхід...' : 'Увійти'}
          </button>
        </form>
        <p className="mt-4 text-sm text-center text-slate-500">
          <Link href="/password-reset" className="text-blue-600 hover:underline">Забули пароль?</Link>
        </p>
        <p className="mt-2 text-sm text-center text-slate-500">
          Немає акаунту? <Link href="/register" className="text-blue-600 hover:underline">Реєстрація</Link>
        </p>
      </div>
    </div>
  );
}
