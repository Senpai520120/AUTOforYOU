import { apiPost, ApiError } from '@/api/client';

/** 403 з кодом email_not_verified: дія потребує підтвердженого email (задача 1.6). */
export function isEmailNotVerified(err: unknown): boolean {
  return err instanceof ApiError && err.status === 403
    && (err.data as { code?: string } | null)?.code === 'email_not_verified';
}

/**
 * Текст помилки повторної відправки листа. 503 — пошта не налаштована (задача 3.4a): показуємо `detail`
 * з відповіді («Відправка листів тимчасово не налаштована…»), а не загальну помилку.
 */
export function resendErrorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return 'Забагато спроб. Спробуйте пізніше.';
    const detail = (err.data as { detail?: unknown } | null)?.detail;
    if (err.status === 503 && typeof detail === 'string' && detail) return detail;
  }
  return 'Не вдалося надіслати лист. Спробуйте пізніше.';
}

export function resendVerificationEmail() {
  return apiPost<unknown>('/api/v1/auth/verify-email/resend/');
}
