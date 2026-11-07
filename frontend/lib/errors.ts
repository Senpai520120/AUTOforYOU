/**
 * Єдиний розбір помилок API для користувача (задача 6.2, 08-Q16).
 * Текст винятку сервера (5xx) не показуємо.
 */
import { ApiError } from '@/api/client';

export { ApiError };

function firstMessage(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null;
  if (Array.isArray(value)) {
    for (const v of value) {
      const m = firstMessage(v);
      if (m) return m;
    }
    return null;
  }
  if (value && typeof value === 'object') {
    for (const v of Object.values(value as Record<string, unknown>)) {
      const m = firstMessage(v);
      if (m) return m;
    }
  }
  return null;
}

/** Перше повідомлення з тіла 400: detail, non_field_errors, далі перше поле. */
export function firstDataMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return firstMessage(data);
  const obj = data as Record<string, unknown>;
  return firstMessage(obj.detail) ?? firstMessage(obj.non_field_errors) ?? firstMessage(obj);
}

export function getErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Немає з'єднання з сервером";
  const { status } = err;
  if (status === 401 || status === 403) return 'Немає доступу';
  if (status === 404) return 'Не знайдено';
  if (status === 429) return 'Забагато запитів, спробуйте пізніше';
  if (status >= 500) return 'Сервіс тимчасово недоступний';
  return firstDataMessage(err.data) ?? 'Не вдалося виконати запит';
}
