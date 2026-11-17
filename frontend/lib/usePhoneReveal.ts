'use client';
/**
 * Показ телефону продавця — один стан для блоку на сторінці і нижньої панелі (задачі 4.5a, 6.6).
 *
 * Вхід: GET /contact/ одразу. Гість: `reveal()` лише розгортає капчу в блоці на сторінці
 * (GuestPhoneReveal), друга капча і обхід перевірки неможливі — номер приходить тільки через `onGuestPhone`.
 */
import { useCallback, useRef, useState } from 'react';
import { ApiError } from '@/api/client';
import { localApi } from '@/api/local';
import { trackEvent } from '@/lib/analytics';
import { apiErrorText, isCaptchaFailed } from '@/lib/captcha';

const GENERIC_ERROR = 'Не вдалося завантажити номер. Спробуйте ще раз.';
export const PHONE_BLOCK_ID = 'phone-block';

export function phoneErrorText(err: unknown): string {
  if (isCaptchaFailed(err)) return 'Не вдалося пройти перевірку. Спробуйте ще раз.';
  if (err instanceof ApiError && err.status === 404) return 'Оголошення більше недоступне.';
  if (err instanceof ApiError && (err.status === 429 || err.status === 503)) return apiErrorText(err, GENERIC_ERROR);
  return GENERIC_ERROR;
}

export function usePhoneReveal(listingId: number, isGuest: boolean) {
  const [phone, setPhone] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [guestOpen, setGuestOpen] = useState(false);
  const inFlight = useRef(false); // подвійний тап до перерисовки не шле другий запит

  const onGuestPhone = useCallback((value: string) => {
    setPhone(value);
    trackEvent('phone_reveal', { source: 'listing' });
  }, []);

  const reveal = useCallback(async () => {
    if (phone || inFlight.current) return;
    if (isGuest) {
      setGuestOpen(true);
      // Капча — у блоці на сторінці: показуємо його, а не малюємо другу.
      document.getElementById(PHONE_BLOCK_ID)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    inFlight.current = true;
    setLoading(true);
    setError('');
    try {
      const data = await localApi.getContact(listingId);
      setPhone(data.contact_phone || 'Номер не вказано');
      trackEvent('phone_reveal', { source: 'listing' });
    } catch (err) {
      setError(phoneErrorText(err)); // 429 — текст добового ліміту з сервера
      // помилку видно в блоці на сторінці: прокручуємо до нього (натиск міг бути з панелі)
      document.getElementById(PHONE_BLOCK_ID)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [phone, isGuest, listingId]);

  return { phone, loading, error, guestOpen, setGuestOpen, reveal, onGuestPhone };
}
