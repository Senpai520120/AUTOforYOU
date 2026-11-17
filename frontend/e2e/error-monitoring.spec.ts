/**
 * E2E: звіти про помилки фронтенду в моніторинг (задача 7.6, 08-Q17).
 *
 * Ендпоінт `POST /api/v1/monitoring/client-errors/` приймає мінімальний звіт без сесії і CSRF,
 * ліміт client_errors на IP (20/год за замовчуванням) — тест на 429 іде останнім.
 */
import { test, expect } from './fixtures';

test.use({ storageState: { cookies: [], origins: [] } });

const URL = '/api/v1/monitoring/client-errors/';

test.describe.serial('Моніторинг помилок фронтенду', () => {
  test('успіх: сторінка помилки з посиланням «На головну» надсилає звіт', async () => {
    // Помилку рендеру в e2e-стеку не викликати без тестової сторінки: SSR-запити до API
    // браузер не перехоплює, а клієнтські сторінки помилки API обробляють самі.
    test.fixme(true, '7.6-error-page → 7.6b (тестова ситуація для error.tsx)');
  });

  test('успіх: звіт зі сторінки сайту (той самий origin, без cookie) → 204', async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
    await page.goto('/');
    const status = await page.evaluate(async (url) => {
      const resp = await fetch(url, {
        method: 'POST', keepalive: true, credentials: 'omit',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: '[E2E] test error', digest: 'e2e', path: '/local/1', component: 'frontend' }),
      });
      return resp.status;
    }, URL);
    expect(status).toBe(204);
  });

  test('обхід: сміттєвий JSON → 400; GET → 405; потік запитів → 429', async ({ request }) => {
    const bad = await request.post(URL, { data: { msg: 'no message field' } });
    expect(bad.status()).toBe(400);
    const huge = await request.post(URL, { data: { message: 'x', digest: 'y'.repeat(5000) } });
    expect(huge.status()).toBe(400);
    expect((await request.get(URL)).status()).toBe(405);
    let last = 0;
    for (let i = 0; i < 25 && last !== 429; i++) {
      last = (await request.post(URL, { data: { message: `[E2E] flood ${i}` } })).status();
    }
    expect(last).toBe(429);
  });
});
