/**
 * E2E: калькулятор — електро/PHEV з ємністю батареї, порожні числові поля не йдуть як 0 (задача 2.5, 23-P17).
 */
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

test.use({ storageState: { cookies: [], origins: [] } });

const isCalc = (r: { url(): string; method(): string }) =>
  r.url().includes('/api/v1/pricing/calculate/') && r.method() === 'POST';

async function submitAndGetBody(page: Page) {
  const reqPromise = page.waitForRequest(isCalc);
  const respPromise = page.waitForResponse((r) => isCalc(r.request()));
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  const req = await reqPromise;
  const resp = await respPromise;
  return { body: JSON.parse(req.postData() ?? '{}') as Record<string, unknown>, status: resp.status() };
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  await page.goto('/calculator');
});

test('успіх: «Електро» → поле батареї → 75 → акциз не 0, «Орієнтовний розрахунок»', async ({ page }) => {
  await page.getByLabel('Тип палива').selectOption('electric');
  const battery = page.getByLabel('Ємність батареї (кВт·год)');
  await expect(battery).toBeVisible();
  await battery.fill('75');
  const { body, status } = await submitAndGetBody(page);
  expect(status).toBe(201);
  expect(body.battery_capacity_kwh).toBe('75');
  await expect(page.getByText(/Акциз \((?!0\.00 EUR)[\d.]+ EUR\)/)).toBeVisible();
  await expect(page.getByTestId('calc-estimate-note')).toContainText('Орієнтовний розрахунок');
  await expect(page.getByTestId('calc-estimate-note')).toContainText('Ставки оновлено');
});

test('успіх: PHEV є у списку і рахується з батареєю', async ({ page }) => {
  await page.getByLabel('Тип палива').selectOption('phev');
  await page.getByLabel('Ємність батареї (кВт·год)').fill('18.5');
  const { status } = await submitAndGetBody(page);
  expect(status).toBe(201);
});

test('помилка: «Електро» без батареї — запиту немає, поле невалідне', async ({ page }) => {
  await page.getByLabel('Тип палива').selectOption('electric');
  const battery = page.getByLabel('Ємність батареї (кВт·год)');
  await expectNoRequest(page, isCalc, () => page.getByRole('button', { name: 'Розрахувати' }).click());
  expect(await battery.evaluate((el) => (el as HTMLInputElement).validity.valueMissing)).toBe(true);
});

test('бензин: поля батареї немає, розрахунок як раніше, числа йдуть числами', async ({ page }) => {
  await expect(page.getByLabel('Ємність батареї (кВт·год)')).toHaveCount(0);
  const { body, status } = await submitAndGetBody(page);
  expect(status).toBe(201);
  expect(body.engine_cc).toBe(2000);
  expect(body.vehicle_year).toBe(2020);
  expect(body.battery_capacity_kwh).toBeUndefined();
});

for (const field of ["Об'єм двигуна (см³)", 'Рік випуску']) {
  test(`помилка: порожнє поле «${field}» не відправляється як 0`, async ({ page }) => {
    const input = page.getByLabel(field);
    await input.fill('');
    await expectNoRequest(page, isCalc, () => page.getByRole('button', { name: 'Розрахувати' }).click());
    expect(await input.evaluate((el) => (el as HTMLInputElement).validity.valueMissing)).toBe(true);
    await expect(input).toHaveValue('');
  });
}
