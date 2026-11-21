'use client';
import { useState } from 'react';
import Link from 'next/link';
import { ApiError, apiPost } from '@/api/client';
import Captcha from '@/components/ui/Captcha';
import { apiErrorText, isCaptchaFailed, useAuthConfig, useCaptchaState } from '@/lib/captcha';

export default function PasswordResetRequestPage() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [sent, setSent] = useState('');
  const [loading, setLoading] = useState(false);
  const { config, error: configError } = useAuthConfig();
  const captcha = useCaptchaState();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      const res = await apiPost<{ detail: string }>('/api/v1/auth/password-reset/', { email, ...captcha.payload() });
      setSent(res.detail);
    } catch (err) {
      if (isCaptchaFailed(err)) setError('Підтвердіть, що ви не робот');
      else if (err instanceof ApiError && err.status === 429) setError('Забагато спроб. Спробуйте пізніше.');
      else setError(apiErrorText(err, 'Сервіс тимчасово недоступний. Спробуйте пізніше.'));
    } finally {
      setLoading(false);
      captcha.bump(); // токен капчі одноразовий
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10">
      <div className="bg-card border border-border rounded-2xl p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-foreground mb-2">Скидання пароля</h1>
        {sent ? (
          <div role="status" data-testid="reset-sent">
            <p className="text-foreground text-sm mb-4">{sent}</p>
            <p className="text-muted-foreground text-sm mb-4">Лист може йти кілька хвилин. Перевірте також папку «Спам».</p>
            <Link href="/login" className="text-link hover:underline text-sm">Повернутися до входу</Link>
          </div>
        ) : (
          <>
            <p className="text-muted-foreground text-sm mb-6">
              Вкажіть email акаунту — ми надішлемо посилання для встановлення нового пароля.
            </p>
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label htmlFor="reset-email" className="block text-sm font-semibold text-foreground mb-1">Email</label>
                <input id="reset-email" type="email" autoComplete="email" inputMode="email" required className="w-full border border-input rounded-lg px-3 py-2 text-base"
                  value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <Captcha config={config?.captcha ?? null} onToken={captcha.setToken}
                resetKey={captcha.resetKey} onHoneypot={captcha.setWebsite} />
              {configError && <p className="text-destructive text-sm">Не вдалося завантажити форму. Оновіть сторінку.</p>}
              {error && <p role="alert" data-testid="form-error" className="text-destructive text-sm">{error}</p>}
              <button type="submit" disabled={loading || !captcha.ready}
                className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-bold py-2.5 rounded-xl disabled:opacity-60 transition-colors">
                {loading ? 'Надсилаємо...' : 'Надіслати посилання'}
              </button>
            </form>
            <p className="mt-4 text-sm text-center text-muted-foreground">
              <Link href="/login" className="text-link hover:underline">Повернутися до входу</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
