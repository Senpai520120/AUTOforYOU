import { expect, type Page, type Request } from '@playwright/test';

/**
 * Перевіряє, що під час `action()` і ще `ms` мс після нього НЕ було жодного
 * запиту, що задовольняє `match`.
 *
 * Підписка на `page.on('request')` робиться ДО action(), тому запит не можна
 * пропустити. Миттєва перевірка «результату немає» хибно-зелена: відповідь
 * приходить асинхронно, тож потрібне вікно очікування.
 */
export async function expectNoRequest(
  page: Page,
  match: (r: Request) => boolean,
  action: () => Promise<void>,
  ms = 2000,
): Promise<void> {
  const hits: string[] = [];
  const listener = (r: Request) => {
    if (match(r)) hits.push(`${r.method()} ${r.url()}`);
  };
  page.on('request', listener);
  try {
    await action();
    // Єдине дозволене місце для waitForTimeout: тут чекаємо саме на ВІДСУТНІСТЬ
    // події, тож немає умови, яку можна було б дочекатися через expect/waitFor.
    await page.waitForTimeout(ms);
  } finally {
    page.off('request', listener);
  }
  expect(hits, `Очікували відсутність запиту, але був(ли): ${hits.join(', ')}`).toHaveLength(0);
}
