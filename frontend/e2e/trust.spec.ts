/**
 * E2E: довіра (задача 10.8) - партнер і контакт біля форми, екран після заявки зі строком і кроками,
 * «Про нас», приховування посилань на порожні розділи.
 *
 * Клієнтські компоненти беруть налаштування з /api/v1/site-settings/ - їх підміняємо через page.route.
 * Серверний рендер (підвал, /about, /prigon) кешується на 60 с і page.route його не перехоплює,
 * тому там перевіряємо стан сиду, а порожній стан - Django-тестами та test.fixme.
 */
import type { Page, Request } from '@playwright/test';
import { test, expect } from './fixtures';

const API = process.env.E2E_API_URL ?? 'http://localhost';
const LEADS_URL = (r: Request) => r.url().endsWith('/api/v1/leads/') && r.method() === 'POST';

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

type Patch = Record<string, unknown>;

async function patchSettings(page: Page, patch: Patch) {
  await page.route('**/api/v1/site-settings/', async (r) => {
    const real = await (await r.fetch()).json();
    await r.fulfill({ json: { ...real, ...patch } });
  });
}

async function calculate(page: Page) {
  await page.goto('/calculator');
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  await expect(page.getByRole('heading', { name: 'Залишити заявку брокеру' })).toBeVisible();
}

async function submitLead(page: Page) {
  const form = page.getByTestId('lead-form');
  await form.getByLabel("Ім'я").fill('[E2E] Довіра');
  await form.getByLabel('Телефон').fill('067 123 45 67');
  await form.getByLabel(/обробку персональних даних/).check();
  await form.getByLabel(/передачу моїх контактних даних партнеру/).check();
  const [resp] = await Promise.all([
    page.waitForResponse((r) => LEADS_URL(r.request())),
    form.getByRole('button', { name: 'Надіслати' }).click(),
  ]);
  expect(resp.status()).toBe(201);
}

test.describe('Партнер і контакт біля форми', () => {
  test('успіх: ім\'я партнера і телефон поруч із кнопкою', async ({ page }) => {
    await patchSettings(page, { partner_name: '[E2E] Партнер', phone: '+380500000000' });
    await calculate(page);
    const info = page.getByTestId('lead-partner-info');
    await expect(info).toContainText('Заявку обробляє партнер: [E2E] Партнер');
    await expect(info).toContainText('+380500000000');
  });

  test('обхід: без партнера блоку немає, тупик «недоступні» на місці', async ({ page }) => {
    await patchSettings(page, { partner_name: '', partner_consent_text: '' });
    await calculate(page);
    await expect(page.getByText('Заявки онлайн тимчасово недоступні')).toBeVisible();
    await expect(page.getByTestId('lead-partner-info')).toHaveCount(0);
  });
});

test.describe('Екран після заявки', () => {
  test('успіх: строк і кроки з налаштувань, HTML у кроці виводиться текстом', async ({ page }) => {
    await patchSettings(page, {
      lead_response_hours: 4,
      lead_next_steps: '[E2E] Перший крок\n\n[E2E] <b>Другий</b> крок',
    });
    await calculate(page);
    await submitLead(page);
    const success = page.getByTestId('lead-success');
    await expect(success).toContainText('Ми відповімо протягом 4 год');
    const steps = page.getByTestId('lead-next-steps').getByRole('listitem');
    await expect(steps).toHaveCount(2);
    await expect(steps.nth(0)).toHaveText('[E2E] Перший крок');
    await expect(steps.nth(1)).toHaveText('[E2E] <b>Другий</b> крок');
  });

  test('обхід: без строку й кроків їх немає, стара фраза лишається', async ({ page }) => {
    await patchSettings(page, { lead_response_hours: null, lead_next_steps: '' });
    await calculate(page);
    await submitLead(page);
    const success = page.getByTestId('lead-success');
    await expect(success).toContainText("Брокер зв'яжеться з вами найближчим часом");
    await expect(success).not.toContainText('Ми відповімо протягом');
    await expect(page.getByTestId('lead-next-steps')).toHaveCount(0);
  });
});

test.describe('Про нас', () => {
  async function aboutText(request: import('@playwright/test').APIRequestContext): Promise<string> {
    const data = await (await request.get(`${API}/api/v1/site-settings/`)).json();
    return (data.about_text ?? '').trim();
  }

  test('успіх: текст із сиду і посилання в підвалі', async ({ page, request }) => {
    test.skip(!(await aboutText(request)), 'about_text порожній (стек без e2e_seed)');
    test.setTimeout(120_000);
    // Сторінка й підвал кешуються на 60 с: якщо їх відкрили до сиду, перезавантажуємо.
    await expect(async () => {
      await page.goto('/about');
      await expect(page.getByTestId('about-text')).toContainText('[E2E]', { timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await expect(page.locator('footer').getByRole('link', { name: 'Про нас' })).toBeVisible();
  });

  test('обхід: порожній текст - 404 і немає посилання в підвалі', async ({ page, request }) => {
    test.fixme(!!(await aboutText(request)), 'TRUST-1 → 10.8: порожній стан недосяжний на сидованому стеку (покрито Django-тестами)');
    const res = await page.goto('/about');
    expect(res?.status()).toBe(404);
    await expect(page.locator('footer').getByRole('link', { name: 'Про нас' })).toHaveCount(0);
  });
});

test.describe('Приховування посилань на порожній розділ', () => {
  async function published(request: import('@playwright/test').APIRequestContext): Promise<boolean> {
    const data = await (await request.get(`${API}/api/v1/content/how-it-works/`)).json();
    return data.published === true;
  }

  test('калькулятор: посилання «Як працює пригон» за станом API', async ({ page, request }) => {
    const on = await published(request);
    await page.goto('/calculator');
    const link = page.getByTestId('calc-link-how-it-works');
    if (on) await expect(link).toBeVisible();
    else {
      await expect(page.getByTestId('calculator-how-we-count')).toBeVisible();
      await expect(link).toHaveCount(0);
    }
  });

  test('обхід: порожній розділ - /how-it-works усе ще 200 з how-it-works-empty', async ({ page, request }) => {
    test.fixme(await published(request), 'TRUST-1 → 10.8: на сидованому стеку розділ опубліковано, порожній стан недосяжний');
    const res = await page.goto('/how-it-works');
    expect(res?.status()).toBe(200);
    await expect(page.getByTestId('how-it-works-empty')).toBeVisible();
  });
});
