/**
 * E2E: калькулятор будує форму з /api/v1/pricing/rates/, демо-банер — за is_demo з API,
 * помилки — людськими повідомленнями без сирого JSON (задача 2.6: 23-P16, 23-P18, 09-Q3, Q5).
 */
import type { Page, Route } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';
import type { CalcRatesResponse, CalcResult } from '../lib/types';

test.use({ storageState: { cookies: [], origins: [] } });

const DEMO_TITLE = 'Тестові тарифи — розрахунок демонстраційний';
const isRates = (url: URL) => url.pathname.endsWith('/api/v1/pricing/rates/');
const isCalc = (r: { url(): string; method(): string }) =>
  r.url().includes('/api/v1/pricing/calculate/') && r.method() === 'POST';

async function patchRates(page: Page, patch: (body: CalcRatesResponse) => CalcRatesResponse) {
  await page.route(isRates, async (route: Route) => {
    const real = await route.fetch();
    await route.fulfill({ response: real, json: patch(await real.json()) });
  });
}

async function patchCalc(page: Page, patch: (body: CalcResult) => CalcResult) {
  await page.route('**/api/v1/pricing/calculate/', async (route: Route) => {
    const real = await route.fetch();
    await route.fulfill({ response: real, json: patch(await real.json()) });
  });
}

async function calculate(page: Page) {
  const resp = page.waitForResponse((r) => isCalc(r.request()));
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  return resp;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Калькулятор: довідники з API', () => {
  test('сид-тарифи неперевірені — банер на формі й у результаті', async ({ page }) => {
    await page.goto('/calculator');
    await expect(page.getByText(DEMO_TITLE)).toHaveCount(1);
    await calculate(page);
    await expect(page.getByTestId('calc-result')).toBeVisible();
    await expect(page.getByText(DEMO_TITLE)).toHaveCount(2);
  });

  test('is_demo:false у /rates/ і /calculate/ — банера немає, мʼяка позначка лишається', async ({ page }) => {
    await patchRates(page, (b) => ({ ...b, is_demo: false }));
    await patchCalc(page, (b) => ({ ...b, is_demo: false, rules_confirmed: false }));
    await page.goto('/calculator');
    await expect(page.getByLabel('Тип палива')).toBeVisible();
    await expect(page.getByTestId('demo-banner')).toHaveCount(0);
    await calculate(page);
    await expect(page.getByTestId('calc-result')).toBeVisible();
    await expect(page.getByTestId('demo-banner')).toHaveCount(0);
    await expect(page.getByTestId('calc-estimate-note')).toContainText('Орієнтовний розрахунок');
  });

  test('Q5: правило звірене і ставки перевірені — без позначки «орієнтовний розрахунок»', async ({ page }) => {
    await patchCalc(page, (b) => ({ ...b, is_demo: false, rules_confirmed: true }));
    await page.goto('/calculator');
    await calculate(page);
    await expect(page.getByTestId('calc-result')).toBeVisible();
    await expect(page.getByTestId('calc-estimate-note')).not.toContainText('Орієнтовний розрахунок');
  });

  test('порт, доданий в адмінці, зʼявляється в select', async ({ page }) => {
    await patchRates(page, (b) => {
      const o = b.options;
      return {
        ...b,
        options: {
          ...o,
          eu_ports: [...o.eu_ports, { value: 'rotterdam', label: 'Rotterdam' }],
          us_ports: o.us_ports.map((p) => ({ ...p, eu_ports: [...p.eu_ports, 'rotterdam'] })),
        },
      };
    });
    await page.goto('/calculator');
    await expect(page.getByLabel('Порт ЄС').locator('option[value="rotterdam"]')).toHaveCount(1);
  });

  test('порожні довідники — «Калькулятор ще не налаштовано», форми немає', async ({ page }) => {
    await patchRates(page, (b) => ({ ...b, options: { ...b.options, is_configured: false, auctions: [] } }));
    await page.goto('/calculator');
    await expect(page.getByTestId('calc-not-configured')).toContainText('Калькулятор ще не налаштовано');
    await expect(page.getByRole('button', { name: 'Розрахувати' })).toHaveCount(0);
  });

  test('підписи ставок — з відповіді: бензин «Мито 10%», електро «Мито 0%»', async ({ page }) => {
    await page.goto('/calculator');
    await calculate(page);
    await expect(page.getByRole('cell', { name: 'Мито 10%', exact: true })).toBeVisible();
    await page.getByLabel('Тип палива').selectOption('electric');
    await page.getByLabel('Ємність батареї (кВт·год)').fill('75');
    await calculate(page);
    await expect(page.getByRole('cell', { name: 'Мито 0%', exact: true })).toBeVisible();
  });
});

test.describe('Калькулятор: помилки без сирого JSON', () => {
  const cases = [
    { status: 422, body: { error: 'not_configured', missing_count: 2 }, text: 'не налаштовано' },
    { status: 429, body: { detail: 'Request was throttled.' }, text: 'Забагато розрахунків' },
    { status: 500, body: { error: 'internal_error' }, text: 'Не вдалося виконати розрахунок' },
  ];
  for (const c of cases) {
    test(`${c.status} — «${c.text}»`, async ({ page }) => {
      await page.route('**/api/v1/pricing/calculate/', (r) => r.fulfill({ status: c.status, json: c.body }));
      await page.goto('/calculator');
      await page.getByRole('button', { name: 'Розрахувати' }).click();
      const alert = page.getByTestId('calc-error');
      await expect(alert).toContainText(c.text);
      await expect(alert).not.toContainText('{');
      await expect(alert).not.toContainText('missing');
      await expect(alert).not.toContainText('internal_error');
    });
  }

  test('400 — повідомлення під полем', async ({ page }) => {
    await page.route('**/api/v1/pricing/calculate/', (r) =>
      r.fulfill({ status: 400, json: { engine_cc: ['Значення завелике.'] } }));
    await page.goto('/calculator');
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await expect(page.getByTestId('error-engine_cc')).toHaveText('Значення завелике.');
  });
});

test.describe('Калькулятор зі сторінки лота (09-Q3)', () => {
  const url = '/calculator?engine_cc=1800&fuel_type=diesel&year=2017&auction=iaai&listing=7';

  test('ціна аукціону порожня, параметри авто заповнені', async ({ page }) => {
    await page.goto(url);
    await expect(page.getByLabel('Ціна аукціону ($)', { exact: true })).toHaveValue('');
    await expect(page.getByLabel("Об'єм двигуна (см³)", { exact: true })).toHaveValue('1800');
    await expect(page.getByLabel('Тип палива')).toHaveValue('diesel');
    await expect(page.getByLabel('Рік випуску', { exact: true })).toHaveValue('2017');
    await expect(page.getByText('Вкажіть ставку на аукціоні в USD')).toBeVisible();
  });

  test('порожня ціна — запит не йде', async ({ page }) => {
    await page.goto(url);
    const price = page.getByLabel('Ціна аукціону ($)', { exact: true });
    await expectNoRequest(page, isCalc, () => page.getByRole('button', { name: 'Розрахувати' }).click());
    expect(await price.evaluate((el: HTMLInputElement) => el.validity.valueMissing)).toBe(true);
  });
});

test('@mobile форма калькулятора без горизонтального скролу на 375 px', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto('/calculator');
  await expect(page.getByLabel('Тип палива')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});
