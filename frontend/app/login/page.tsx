'use client';
import { Suspense, useId, useState } from 'react';
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

// Відмова входу через SSO: бекенд повертає на /login?sso_error=<код> без подробиць (users/oidc_views.py).
const SSO_ERRORS: Record<string, string> = {
  no_account: 'Акаунта з цим email ще немає. Спочатку зареєструйтеся з цим email, потім входьте через SSO.',
  not_allowed: 'Вхід через SSO для цього акаунта недоступний. Увійдіть паролем або зверніться до підтримки.',
  cancelled: 'Вхід через SSO скасовано.',
  throttled: 'Забагато спроб. Спробуйте пізніше.',
  failed: 'Не вдалося увійти через SSO. Спробуйте ще раз.',
};

function LoginForm() {
  const { login } = useAuth();
  const emailId = useId();
  const passwordId = useId();
  const router = useRouter();
  const params = useSearchParams();
  // Повернення тільки на шлях цього сайту (08-S7, 10-S7).
  const next = safeNext(params.get('next'));
  const ssoErrorCode = params.get('sso_error');
  const ssoError = ssoErrorCode ? (SSO_ERRORS[ssoErrorCode] ?? SSO_ERRORS.failed) : '';
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
        {ssoError && <p role="alert" className="mb-4 text-red-600 text-sm">{ssoError}</p>}
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor={emailId} className="block text-sm font-semibold text-slate-700 mb-1">Email</label>
            <input id={emailId} type="email" autoComplete="email" required className="w-full border border-slate-300 rounded-lg px-3 py-2"
              value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div>
            <label htmlFor={passwordId} className="block text-sm font-semibold text-slate-700 mb-1">Пароль</label>
            <input id={passwordId} type="password" autoComplete="current-password" required className="w-full border border-slate-300 rounded-lg px-3 py-2"
              value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          {showCaptcha && (
            <Captcha config={config?.captcha ?? null} onToken={captcha.setToken}
              resetKey={captcha.resetKey} onHoneypot={captcha.setWebsite} />
          )}
          {error && <p role="alert" className="text-red-600 text-sm">{error}</p>}
          <button type="submit" disabled={loading || (showCaptcha && !captcha.ready)}
            className="w-full bg-blue-700 hover:bg-blue-800 text-white font-bold py-2.5 rounded-xl disabled:opacity-60 transition-colors">
            {loading ? 'Вхід...' : 'Увійти'}
          </button>
        </form>
        {config?.oidc_enabled && config.oidc_start_url && (
          // Звичайне посилання, не fetch: далі редіректи на Keycloak і назад (задача SSO-1).
          <a href={`${config.oidc_start_url}?${new URLSearchParams({ next })}`}
            className="mt-3 block w-full text-center border border-slate-300 hover:border-blue-400 text-slate-700 font-semibold py-2.5 rounded-xl transition-colors">
            Увійти через SSO
          </a>
        )}
        <p className="mt-4 text-sm text-center text-slate-500">
          <Link href="/password-reset" className="text-blue-600 hover:underline">Забули пароль?</Link>
        </p>
        <p className="mt-2 text-sm text-center text-slate-500">
          Немає акаунту? <Link href="/register" className="text-blue-600 underline">Реєстрація</Link>
        </p>
      </div>
    </div>
  );
}
