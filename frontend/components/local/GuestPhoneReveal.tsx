'use client';
/**
 * Телефон продавця гостю після капчі (задача 4.5a, F3.2/Q2).
 *
 * «Показати телефон» розгортає капчу (Turnstile або honeypot з /auth/config/), «Показати номер»
 * шле POST /contact/ з токеном. Відмови показуються текстом сервера: капча, добовий ліміт (429),
 * показ гостям вимкнено (503), оголошення недоступне (404). Номер у DOM з'являється лише після 200.
 * Стан «розгорнуто» керується ззовні (usePhoneReveal, 6.6): нижня панель відкриває цю ж капчу.
 */
import { useState } from 'react';
import Link from 'next/link';
import Captcha from '@/components/ui/Captcha';
import { localApi } from '@/api/local';
import { useAuthConfig, useCaptchaState } from '@/lib/captcha';
import { phoneErrorText } from '@/lib/usePhoneReveal';

/** @deprecated назва 4.5a; те саме, що phoneErrorText. */
export const guestPhoneError = phoneErrorText;

export default function GuestPhoneReveal({ listingId, open, onOpen, onPhone }: {
  listingId: number;
  open: boolean;
  onOpen: () => void;
  onPhone: (phone: string) => void;
}) {
  if (!open) {
    return (
      <button
        type="button"
        onClick={onOpen}
        className="w-full bg-blue-700 hover:bg-blue-600 text-white font-semibold py-2.5 rounded-lg transition-colors"
      >
        Показати телефон
      </button>
    );
  }
  return <GuestCaptchaForm listingId={listingId} onPhone={onPhone} />;
}

function GuestCaptchaForm({ listingId, onPhone }: { listingId: number; onPhone: (phone: string) => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { config, error: configError } = useAuthConfig();
  const captcha = useCaptchaState();

  const submit = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await localApi.getContactAsGuest(listingId, captcha.payload());
      onPhone(data.contact_phone || 'Номер не вказано');
    } catch (err) {
      setError(phoneErrorText(err));
    } finally {
      setLoading(false);
      captcha.bump(); // токен одноразовий
    }
  };

  return (
    <div className="space-y-2" data-testid="guest-phone">
      <p className="text-xs text-slate-500">Підтвердіть, що ви не робот, щоб побачити номер.</p>
      {config?.captcha.provider !== 'honeypot' && (
        <div aria-hidden="true" style={{ position: 'absolute', left: '-10000px', width: 1, height: 1, overflow: 'hidden' }}>
          <input type="text" name="website" tabIndex={-1} autoComplete="off" defaultValue=""
            onChange={(e) => captcha.setWebsite(e.target.value)} />
        </div>
      )}
      <Captcha config={config?.captcha ?? null} onToken={captcha.setToken}
        resetKey={captcha.resetKey} onHoneypot={captcha.setWebsite} />
      <button
        type="button"
        onClick={submit}
        disabled={!captcha.ready || loading}
        className="w-full bg-blue-700 hover:bg-blue-600 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg transition-colors"
      >
        {loading ? 'Завантаження...' : 'Показати номер'}
      </button>
      {(error || configError) && (
        <p role="alert" className="text-xs text-red-600">
          {error || 'Не вдалося завантажити перевірку. Спробуйте пізніше.'}
        </p>
      )}
      <p className="text-xs text-slate-500">
        Або <Link href="/login" className="text-blue-700 hover:underline">увійдіть</Link> — без перевірки.
      </p>
    </div>
  );
}
