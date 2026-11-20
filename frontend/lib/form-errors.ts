import { ApiError } from '@/api/client';
import { apiErrorText } from '@/lib/captcha';

/**
 * Розкладає 400-відповідь DRF по полях форми (10.28): помилки з ключами `fields` повертаються
 * окремо (їх показують біля поля), решта (капча, detail, non_field_errors) — одним текстом.
 */
export function splitFieldErrors(
  err: unknown,
  fields: readonly string[],
  fallback: string,
): { fieldErrors: Record<string, string>; general: string } {
  const fieldErrors: Record<string, string> = {};
  if (!(err instanceof ApiError) || !err.data || typeof err.data !== 'object') {
    return { fieldErrors, general: apiErrorText(err, fallback) };
  }
  const rest: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(err.data as Record<string, unknown>)) {
    const text = Array.isArray(value) ? value.map(String).join('. ') : typeof value === 'string' ? value : '';
    if (fields.includes(key) && text) fieldErrors[key] = text;
    else rest[key] = value;
  }
  if (!Object.keys(fieldErrors).length) return { fieldErrors, general: apiErrorText(err, fallback) };
  const restText = apiErrorText(new ApiError(err.status, rest), '');
  return { fieldErrors, general: restText };
}

/** Фокус на перше поле з aria-invalid="true" усередині форми (підхід LeadForm, 10.12). */
export function focusFirstInvalid(form: HTMLFormElement | null) {
  const el = form?.querySelector<HTMLElement>('[aria-invalid="true"]');
  if (!el) return;
  el.scrollIntoView({ block: 'center' });
  el.focus({ preventScroll: true });
}
