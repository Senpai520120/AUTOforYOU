/**
 * E2E: доставка по Україні та послуги брокера в розрахунку (задача 2.7, 09-Q5).
 * Дані — демо-рядки e2e_seed: «[E2E] Київ» $300, «[E2E] Ужгород» (ціна за запитом), «[E2E] Послуги брокера» $500.
 */
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { fillCalcForm } from './helpers/calc-form';

test.use({ storageState: { cookies: [], origins: [] } });

const isCalc = (r: { url(): string; method(): string }) =>
  r.url().includes('/api/v1/pricing/calculate/') && r.method() === 'POST';

async function calculate(page: Page) {
  const resp = page.waitForResponse((r) => isCalc(r.request()));
  await fillCalcForm(page);
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  return resp;
}

// 10.1: «РАЗОМ» тепер з копійками, роздільник залежить від локалі (крапка чи кома) — розбираємо обидва.
// 10.17: формат uk-UA — тисячі розділені U+00A0 (або U+202F), десяткова кома; усе, крім цифр і .,, знімається нижче.
const money = (text: string) => {
  const t = text.replace(/[^\d.,]/g, '');
  const m = t.match(/^(.*?)[.,](\d{1,2})$/);
  return m ? Number(`${m[1].replace(/[.,]/g, '')}.${m[2]}`) : Number(t.replace(/[.,]/g, ''));
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test('місто обрано — доставка й послуги брокера з сумами, дати курсу й тарифів, підсумок їх включає', async ({ page }) => {
  await page.goto('/calculator');
  const totalOf = async () => money(await page.getByRole('row').filter({ hasText: 'РАЗОМ' }).getByRole('cell').nth(1).innerText());

  const first = (await (await calculate(page)).json()).breakdown;
  const withoutCity = await totalOf();

  await page.getByLabel('Доставка по Україні (місто)').selectOption({ label: '[E2E] Київ' });
  const resp = await calculate(page);
  expect(resp.status()).toBe(201);
  const delivery = page.getByRole('row').filter({ hasText: 'Доставка по Україні' });
  await expect(delivery).toContainText('$300');
  await expect(page.getByRole('row').filter({ hasText: '[E2E] Послуги брокера' })).toContainText('$500');
  await expect(page.getByTestId('calc-estimate-note')).toContainText('Курс НБУ на');
  await expect(page.getByTestId('calc-estimate-note')).toContainText('Тарифи на');
  // доставка по Україні (300) йде після розмитнення — подорожчання на неї рівно в USD, без податків
  const b = (await resp.json()).breakdown;
  expect(Number(b.total_usd_full) - Number(first.total_usd_full)).toBeCloseTo(Number(b.ua_delivery_usd), 2);
  expect(await totalOf()).toBeCloseTo(withoutCity + Number(b.ua_delivery_usd), 2);
  // 10.1: «РАЗОМ» у USD = breakdown.total_usd_full (з акцизом, ПДВ і пенсійним збором), більше за total_usd
  expect(Number(b.total_usd_full)).toBeGreaterThan(Number(b.total_usd));
  expect(await totalOf()).toBeCloseTo(Number(b.total_usd_full), 2);
});

test('без міста — «уточнюється менеджером», сторінка не падає', async ({ page }) => {
  await page.goto('/calculator');
  const resp = await calculate(page);
  const body = await resp.json();
  expect(body.breakdown.ua_delivery_pending).toBe(true);
  await expect(page.getByRole('row').filter({ hasText: 'Доставка по Україні' })).toContainText('уточнюється менеджером');
});

test('місто «ціна за запитом» — у підсумок не входить', async ({ page }) => {
  await page.goto('/calculator');
  await page.getByLabel('Доставка по Україні (місто)').selectOption({ label: '[E2E] Ужгород (ціна за запитом)' });
  await calculate(page);
  await expect(page.getByRole('row').filter({ hasText: 'Доставка по Україні' })).toContainText('уточнюється менеджером');
});

test('гостю в /rates/ немає сум доставки та послуг (Q11)', async ({ page }) => {
  const resp = await page.request.get('/api/v1/pricing/rates/');
  const raw = JSON.stringify({ a: (await resp.json()).ua_delivery_rates, b: (await resp.json()).broker_service_fees });
  expect(raw).toContain('[E2E] Київ');
  expect(raw).not.toContain('cost_usd');
  expect(raw).not.toContain('amount_usd');
});

test('підмінений id (400) — повідомлення під полем, без сирого JSON', async ({ page }) => {
  await page.route('**/api/v1/pricing/calculate/', (r) =>
    r.fulfill({ status: 400, json: { ua_delivery_rate: ['Доставка до цього міста зараз недоступна. Оберіть інше.'] } }));
  await page.goto('/calculator');
  await fillCalcForm(page);
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  await expect(page.getByTestId('error-ua_delivery_rate')).toHaveText('Доставка до цього міста зараз недоступна. Оберіть інше.');
  await expect(page.getByTestId('calc-error')).not.toContainText('{');
});
