'use client';
/**
 * Телефон продавця гостю після капчі (задача 4.5a, F3.2/Q2).
 *
 * «Показати телефон» розгортає капчу (Turnstile або honeypot з /auth/config/), «Показати номер»
 * шле POST /contact/ з токеном. Відмови показуються текстом сервера: капча, добовий ліміт (429),
 * показ гостям вимкнено (503), оголошення недоступне (404). Номер у DOM з'являється лише після 200.
 * Стан «розгорнуто» керується ззовні (usePhoneReveal, 6.6): нижня панель відкриває цю ж капчу.
 */
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import Captcha from '@/components/ui/Captcha';
import { localApi } from '@/api/local';
import { useAuthConfig, useCaptchaState } from '@/lib/captcha';
import { phoneErrorText } from '@/lib/usePhoneReveal';
import { CircleAlert, Phone } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { ICON_STROKE } from '@/lib/utils';

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
      <Button type="button" size="lg" onClick={onOpen} className="w-full font-semibold">
        <Phone strokeWidth={ICON_STROKE} aria-hidden="true" />
        Показати телефон
      </Button>
    );
  }
  return <GuestCaptchaForm listingId={listingId} onPhone={onPhone} />;
}

function GuestCaptchaForm({ listingId, onPhone }: { listingId: number; onPhone: (phone: string) => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { config, error: configError } = useAuthConfig();
  const captcha = useCaptchaState();
  const boxRef = useRef<HTMLDivElement>(null);

  // 10.25: нижня панель відкрила капчу — прокручуємо і ставимо фокус на блок (клавіатура і скрінрідер).
  useEffect(() => {
    const el = boxRef.current;
    el?.scrollIntoView({ block: 'center' });
    el?.focus({ preventScroll: true });
  }, []);

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
    <div ref={boxRef} tabIndex={-1} role="group" aria-label="Перевірка перед показом номера"
      className="space-y-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg" data-testid="guest-phone">
      <p className="text-xs text-muted-foreground">Підтвердіть, що ви не робот, щоб побачити номер.</p>
      {config?.captcha.provider !== 'honeypot' && (
        <div aria-hidden="true" style={{ position: 'absolute', left: '-10000px', width: 1, height: 1, overflow: 'hidden' }}>
          <input type="text" name="website" tabIndex={-1} autoComplete="off" defaultValue=""
            onChange={(e) => captcha.setWebsite(e.target.value)} />
        </div>
      )}
      <Captcha config={config?.captcha ?? null} onToken={captcha.setToken}
        resetKey={captcha.resetKey} onHoneypot={captcha.setWebsite} />
      <Button type="button" size="lg" onClick={submit} disabled={!captcha.ready || loading} className="w-full font-semibold">
        {loading ? 'Завантаження...' : 'Показати номер'}
      </Button>
      {(error || configError) && (
        <p role="alert" className="flex items-start gap-1.5 text-xs text-destructive">
          <CircleAlert className="size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
          {error || 'Не вдалося завантажити перевірку. Спробуйте пізніше.'}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Або <Link href="/login" className="font-medium text-primary underline underline-offset-4">увійдіть</Link> — без перевірки.
      </p>
    </div>
  );
}
