/**
 * Перевірка адреси повернення (?next=, посилання сповіщень) — захист від open-redirect.
 *
 * Дозволено тільки відносний шлях сайту: починається з «/», але не з «//» і не з «/\»
 * (браузер трактує обидва як адресу іншого хоста). Решта — fallback.
 */
export function safeNext(value: string | null | undefined, fallback = '/me'): string {
  if (!value) return fallback;
  if (!/^\/(?![\/\\])/.test(value)) return fallback;
  // Керуючі символи (таб, перенос) браузер вирізає з URL — після цього «/\t/evil» стає «//evil».
  if (/[\u0000-\u001f\u007f]/.test(value)) return fallback;
  return value;
}
