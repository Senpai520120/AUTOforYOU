/**
 * E2E: дневні лічильники без ПДн (задача 8.7). Значення лічильників перевіряють Django-тести (metrics/tests.py);
 * тут — що фронт шле рівно одну подію без cookie й ідентифікаторів і що збій лічильника не ламає калькулятор.
 */
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

test.use({ storageState: { cookies: [], origins: [] } });

const isEvent = (r: { url(): string; method(): string }) =>
  r.url().includes('/api/v1/metrics/event/') && r.method() === 'POST';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test('візит калькулятора — один POST {key:"calculator_visit"} без cookie; перезавантаження вкладки другого не шле', async ({ page }) => {
  const reqPromise = page.waitForRequest(isEvent);
  await page.goto('/calculator');
  const req = await reqPromise;
  expect(JSON.parse(req.postData() ?? '{}')).toEqual({ key: 'calculator_visit' });
  const headers = await req.allHeaders();
  expect(headers['cookie']).toBeUndefined();
  expect((await req.response())?.status()).toBe(204);

  await expectNoRequest(page, isEvent, async () => {
    await page.reload();
    await expect(page.getByLabel('Тип палива')).toBeVisible();
  });
});

test('лічильник недоступний (500 / обрив) — калькулятор рахує без видимих помилок', async ({ page }) => {
  await page.route('**/api/v1/metrics/event/', (r) => r.abort());
  await page.goto('/calculator');
  const resp = page.waitForResponse((r) => r.url().includes('/api/v1/pricing/calculate/'));
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  expect((await resp).status()).toBe(201);
  await expect(page.getByTestId('calc-result')).toBeVisible();
  await expect(page.getByTestId('calc-error')).toHaveCount(0);
});

test('обхід: ручний POST із серверним ключем (lead) відхилено', async ({ page }) => {
  const resp = await page.request.post('/api/v1/metrics/event/', { data: { key: 'lead' } });
  expect(resp.status()).toBe(400);
});
