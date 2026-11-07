/**
 * E2E: аудит калькулятора та каталогу (задача 2.17: E10 дата розрахунку, B6 фільтр ціни).
 * Негативні перевірки йдуть через API (request) і перевіряють код та ключ помилки; UI — що сторінка жива.
 */
import { test, expect } from './fixtures';

test.use({ storageState: { cookies: [], origins: [] } });

const CALC = '/api/v1/pricing/calculate/';
/** Дата в Europe/Kyiv (як localdate на бекенді), зі зсувом у днях. en-CA дає формат YYYY-MM-DD. */
const isoDate = (offsetDays: number) => {
  const fmt = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Kyiv' });
  return fmt.format(new Date(Date.now() + offsetDays * 86_400_000));
};
const payload = (calculation_date: string) => ({
  auction_price_usd: '5000', engine_cc: 2000, fuel_type: 'petrol', vehicle_year: 2018, calculation_date,
});

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test('розрахунок на сьогоднішню дату проходить', async ({ request }) => {
  const res = await request.post(CALC, { data: payload(isoDate(0)) });
  expect(res.status()).toBe(201);
});

test('дата розрахунку в майбутньому — 400 і без ставок у відповіді', async ({ request }) => {
  const res = await request.post(CALC, { data: payload(isoDate(2)) });
  expect(res.status()).toBe(400);
  expect(await res.json()).toEqual({ calculation_date: ['Дата не може бути в майбутньому'] });
});

test('API каталогу: некоректна ціна — 400 з ключем параметра, не 500', async ({ request }) => {
  for (const [param, bad] of [['price_min', 'abc'], ['price_max', '1e999'], ['price_max', '--']]) {
    const res = await request.get('/api/v1/local/listings/', { params: { [param]: bad } });
    expect(res.status(), `${param}=${bad}`).toBe(400);
    expect(Object.keys(await res.json()), `${param}=${bad}`).toEqual([param]);
  }
});

test('/ua?price_min=abc не дає білого екрана', async ({ page }) => {
  const resp = await page.goto('/ua?price_min=abc');
  expect(resp?.status()).toBe(200);
  await expect(page.locator('body')).not.toContainText('Application error');
  await expect(page.getByTestId('ua-filter-error')).toContainText(
    'Некоректне значення фільтра (ціна, рік або пробіг мають бути числом). Змініть фільтри та спробуйте ще раз.',
  );
});
