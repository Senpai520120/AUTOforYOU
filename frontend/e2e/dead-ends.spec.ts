/**
 * E2E: тупики перед заявкою (задача 10.7): запасний контакт із SiteSettings і «Спробувати ще раз».
 * Збої підміняються через page.route; контакти беремо з відповіді, а не з хардкоду.
 */
import type { Page, Request } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

const SETTINGS = '**/api/v1/site-settings/';
const RATES = '**/api/v1/pricing/rates/';
const PHONE = '+380501112233';
const NO_CONTACTS = {
  phone: '', manager_contact: '', support_email: '', telegram_channel_url: '', telegram_bot_username: '',
};
const isSettings = (r: Request) => r.url().endsWith('/api/v1/site-settings/');

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

async function patchSettings(page: Page, patch: Record<string, unknown>) {
  await page.route(SETTINGS, async (r) => {
    const real = await (await r.fetch()).json();
    await r.fulfill({ json: { ...real, ...patch } });
  });
}

async function unconfigured(page: Page) {
  await page.route(RATES, async (r) => {
    const b = await (await r.fetch()).json();
    await r.fulfill({ json: { ...b, options: { ...b.options, is_configured: false, auctions: [] } } });
  });
}

async function openLeadForm(page: Page) {
  await page.goto('/calculator');
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  await expect(page.getByRole('heading', { name: 'Залишити заявку брокеру' })).toBeVisible();
}

test.describe('Форма заявки без партнера', () => {
  test('контакт видно, повтор вмикає форму без перезавантаження', async ({ page }) => {
    let calls = 0;
    let broken = true;
    await page.route(SETTINGS, async (r) => {
      calls += 1;
      const real = await (await r.fetch()).json();
      await r.fulfill({
        json: broken ? { ...real, partner_name: '', partner_consent_text: '', phone: PHONE } : real,
      });
    });
    await openLeadForm(page);
    await expect(page.getByText('Заявки онлайн тимчасово недоступні')).toBeVisible();
    await expect(page.getByTestId('fallback-contact').getByRole('link', { name: PHONE }))
      .toHaveAttribute('href', `tel:${PHONE}`);
    const form = page.getByTestId('lead-form');
    await expect(form.getByLabel(/Згода на передачу контактів партнеру/)).toBeDisabled();

    broken = false;
    const before = calls;
    await page.getByRole('button', { name: 'Спробувати ще раз' }).click();
    await expect(page.getByText('Заявки онлайн тимчасово недоступні')).toHaveCount(0);
    expect(calls - before).toBe(1);
    await expect(form.getByLabel(/передачу моїх контактних даних партнеру/)).toBeEnabled();
  });

  test('без контактів: чесний текст, жодних tel/mailto, кнопка є', async ({ page }) => {
    await patchSettings(page, { partner_name: '', partner_consent_text: '', ...NO_CONTACTS });
    await openLeadForm(page);
    const box = page.getByTestId('lead-unavailable');
    await expect(box.getByTestId('fallback-no-contact'))
      .toHaveText('Зараз ми не можемо прийняти заявку онлайн. Спробуйте ще раз трохи пізніше.');
    await expect(box.locator('a[href^="tel:"], a[href^="mailto:"]')).toHaveCount(0);
    await expect(box.getByRole('button', { name: 'Спробувати ще раз' })).toBeVisible();
  });

  test('налаштування не завантажились (503): той самий стан без контакту', async ({ page }) => {
    await page.route(SETTINGS, (r) => r.fulfill({ status: 503, json: { detail: 'down' } }));
    await openLeadForm(page);
    await expect(page.getByTestId('fallback-no-contact')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Спробувати ще раз' })).toBeVisible();
  });

  test('під час повтору кнопка заблокована і другого запиту немає', async ({ page }) => {
    let calls = 0;
    await page.route(SETTINGS, async (r) => {
      calls += 1;
      if (calls > 1) await new Promise((res) => setTimeout(res, 1500));
      await r.fulfill({ status: 503, json: { detail: 'down' } });
    });
    await openLeadForm(page);
    // На сторінці ще 4 компоненти (банер cookie, аналітика, carVertical, шапка) читають ті ж налаштування
    // при монтуванні; рахуємо тільки запити, що з'явились ПІСЛЯ кліку на повтор.
    await page.waitForLoadState('networkidle');
    const afterLoad = calls;
    await page.getByRole('button', { name: 'Спробувати ще раз' }).click();
    const busy = page.getByRole('button', { name: 'Завантажую…' });
    await expect(busy).toBeDisabled();
    await expectNoRequest(page, isSettings, async () => {
      await busy.click({ force: true }).catch(() => {});
    }, 500);
    await expect(page.getByRole('button', { name: 'Спробувати ще раз' })).toBeEnabled();
    expect(calls - afterLoad).toBe(1);
  });
});

test.describe('Один запит налаштувань (10.16)', () => {
  test('/calculator: за завантаження рівно один запит site-settings', async ({ page }) => {
    const hits: string[] = [];
    page.on('request', (r) => { if (isSettings(r)) hits.push(r.url()); });
    await page.goto('/calculator');
    await expect(page.getByRole('button', { name: 'Розрахувати' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    expect(hits).toHaveLength(1);
  });
});

test.describe('Калькулятор', () => {
  test('довідник не завантажився: контакт, повтор показує форму', async ({ page }) => {
    let broken = true;
    await page.route(RATES, (r) => (broken ? r.abort() : r.continue()));
    await patchSettings(page, { phone: PHONE });
    await page.goto('/calculator');
    await expect(page.getByText('Не вдалося завантажити калькулятор')).toBeVisible();
    await expect(page.getByTestId('fallback-contact').getByRole('link', { name: PHONE })).toBeVisible();
    broken = false;
    await page.getByRole('button', { name: 'Спробувати ще раз' }).click();
    await expect(page.getByRole('button', { name: 'Розрахувати' })).toBeVisible();
  });

  test('не сконфігурований: контакт і кнопка, форми немає', async ({ page }) => {
    await unconfigured(page);
    await patchSettings(page, { phone: PHONE });
    await page.goto('/calculator');
    await expect(page.getByTestId('calc-not-configured')).toContainText('Калькулятор ще не налаштовано');
    await expect(page.getByTestId('fallback-contact')).toContainText(PHONE);
    await expect(page.getByRole('button', { name: 'Спробувати ще раз' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Розрахувати' })).toHaveCount(0);
  });

  test('не сконфігурований і без контактів: чесний текст', async ({ page }) => {
    await unconfigured(page);
    await patchSettings(page, NO_CONTACTS);
    await page.goto('/calculator');
    await expect(page.getByTestId('fallback-no-contact')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Спробувати ще раз' })).toBeVisible();
  });

  test('валідація розрахунку (400): запасного контакту немає', async ({ page }) => {
    await page.route('**/api/v1/pricing/calculate/', (r) =>
      r.fulfill({ status: 400, json: { auction_price_usd: ['Некоректна ціна.'] } }));
    await patchSettings(page, { phone: PHONE });
    await page.goto('/calculator');
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await expect(page.getByTestId('calc-error')).toBeVisible();
    await expect(page.getByTestId('fallback-contact')).toHaveCount(0);
  });

  test('збій розрахунку (503): контакт під помилкою', async ({ page }) => {
    await page.route('**/api/v1/pricing/calculate/', (r) => r.fulfill({ status: 503, json: {} }));
    await patchSettings(page, { phone: PHONE });
    await page.goto('/calculator');
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await expect(page.getByTestId('calc-error').getByTestId('fallback-contact')).toContainText(PHONE);
  });
});
