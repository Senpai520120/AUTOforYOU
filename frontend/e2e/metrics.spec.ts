/**
 * E2E: клієнтські лічильники без ПДн (задача 8.7).
 * Значення лічильників з браузера не читаються (окремого API немає, адмінка — лише для admin-ролі),
 * тому перевіряємо контракт запиту: один POST з {key}, без cookie, відмова на чужий ключ, стійкість до збою.
 */
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

test.use({ storageState: { cookies: [], origins: [] } });

const isMetric = (r: { url(): string; method(): string }) =>
  r.url().includes('/api/v1/metrics/event/') && r.method() === 'POST';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test('відкриття /calculator надсилає один POST {key:calculator_visit} без cookie, перезавантаження — не надсилає', async ({ page }) => {
  const reqPromise = page.waitForRequest(isMetric);
  await page.goto('/calculator');
  const req = await reqPromise;
  expect(req.postDataJSON()).toEqual({ key: 'calculator_visit' });
  const headers = await req.allHeaders();
  expect(headers['cookie']).toBeUndefined();
  expect(headers['authorization']).toBeUndefined();

  await expectNoRequest(page, isMetric, async () => {
    await page.reload();
    await expect(page.getByRole('button', { name: 'Розрахувати' })).toBeVisible();
  });
});

test('збій сервера лічильників не ламає калькулятор', async ({ page }) => {
  await page.route(/\/api\/v1\/metrics\/event\//, (route) => route.abort());
  await page.goto('/calculator');
  await expect(page.getByRole('button', { name: 'Розрахувати' })).toBeVisible();
  const resp = page.waitForResponse((r) => r.url().includes('/api/v1/pricing/calculate/') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  expect((await resp).status()).toBe(201);
  await expect(page.getByTestId('calc-result')).toBeVisible();
  // ошибки калькулятора, а не любой role=alert: его дают и демо-баннер, и анонсер маршрутов Next
  await expect(page.getByTestId('calc-error')).toHaveCount(0);
  await expect(page.getByText('Не вдалося завантажити калькулятор')).toHaveCount(0);
});

test('ручний POST з чужим ключем відхилено 400', async ({ page, request }) => {
  await page.goto('/calculator');
  const url = '/api/v1/metrics/event/';
  for (const body of [{ key: 'lead' }, { key: 'registration' }, { key: 'calculator_visit', user: 1 }]) {
    const r = await request.post(url, { data: body });
    expect(r.status(), JSON.stringify(body)).toBe(400);
  }
  const ok = await request.post(url, { data: { key: 'mobile_bar_click' } });
  expect(ok.status()).toBe(204);
});
