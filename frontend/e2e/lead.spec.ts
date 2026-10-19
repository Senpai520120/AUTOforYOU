/**
 * E2E: заявка брокеру (задача 2.3, 23-P15): форма після розрахунку, лот, джерело, /me/leads.
 * У e2e-стеку немає ключів Turnstile, тож діє honeypot-капча (кнопка активна через ~3 с).
 */
import type { Page, Request } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';
import { expectNoRequest } from './helpers/network';

const LEADS_URL = (r: Request) => r.url().endsWith('/api/v1/leads/') && r.method() === 'POST';
const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

test.beforeEach(async ({ page }) => {
  await page.addInitScript(consentInit);
});

async function calculate(page: Page, path = '/calculator') {
  await page.goto(path);
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  await expect(page.getByRole('heading', { name: 'Залишити заявку брокеру' })).toBeVisible();
}

async function fillLead(page: Page, opts: { name?: string; phone?: string; consent?: boolean } = {}) {
  const form = page.getByTestId('lead-form');
  if (opts.name !== undefined) await form.getByLabel("Ім'я").fill(opts.name);
  if (opts.phone !== undefined) await form.getByLabel('Телефон').fill(opts.phone);
  if (opts.consent !== false) await form.getByLabel(/обробку персональних даних/).check();
  await form.getByLabel(/передачу моїх контактних даних партнеру/).check();
}

const submitBtn = (page: Page) => page.getByTestId('lead-form').getByRole('button', { name: 'Надіслати' });

async function submitAndWait(page: Page) {
  const [resp, req] = await Promise.all([
    page.waitForResponse((r) => LEADS_URL(r.request())),
    page.waitForRequest(LEADS_URL),
    submitBtn(page).click(),
  ]);
  return { resp, body: req.postDataJSON() as Record<string, unknown> };
}

test.describe('Гість', () => {
  test('розрахунок -> заявка -> екран успіху, 201', async ({ page }) => {
    await calculate(page);
    await expect(page.getByText('Сума орієнтовна')).toBeVisible();
    const form = page.getByTestId('lead-form');
    await form.getByLabel("Ім'я").fill('[E2E] Гість');
    await form.getByLabel('Телефон').fill('067 123 45 67');
    await form.getByLabel('Telegram').check();
    await form.getByLabel(/Нік або контакт/).fill('@e2e_guest');
    await form.getByLabel(/обробку персональних даних/).check();
    await form.getByLabel(/передачу моїх контактних даних партнеру/).check();
    const { resp, body } = await submitAndWait(page);
    expect(resp.status()).toBe(201);
    expect(body).toMatchObject({ source: 'calculator', contact_method: 'telegram', contact_handle: '@e2e_guest' });
    expect(body.calculation_id).toBeGreaterThan(0);
    await expect(page.getByTestId('lead-success')).toContainText(/Заявку №AFY-\d{4}-\d+ отримано/);
    await expect(page.getByTestId('lead-form')).toHaveCount(0);
    // Новий розрахунок прибирає результат.
    await page.getByRole('button', { name: 'Новий розрахунок' }).click();
    await expect(page.getByTestId('lead-success')).toHaveCount(0);
  });

  test('Q4: немає WhatsApp, email з поганим форматом -> помилка біля поля, запиту немає', async ({ page }) => {
    await calculate(page);
    const form = page.getByTestId('lead-form');
    await expect(form.getByLabel('WhatsApp')).toHaveCount(0);
    await expect(form.getByLabel('Дзвінок')).toBeChecked();
    await fillLead(page, { name: '[E2E] Email', phone: '0671234567' });
    await form.getByLabel(/^Email/).fill('not-an-email');
    await expectNoRequest(page, LEADS_URL, async () => {
      await submitBtn(page).click();
    });
    await expect(form.getByText('Вкажіть коректний email.')).toBeVisible();
  });

  test('бюджет і місто: заявка приймається, показано код AFY', async ({ page }) => {
    await calculate(page);
    const form = page.getByTestId('lead-form');
    await form.getByRole('button', { name: 'Ще' }).click();
    await form.getByLabel(/Бюджет/).fill('25000');
    await form.getByLabel('Місто').fill('Київ');
    await form.getByLabel('Коли потрібне авто').selectOption('asap');
    await fillLead(page, { name: '[E2E] Бюджет', phone: '+380671234567' });
    const { resp, body } = await submitAndWait(page);
    expect(resp.status()).toBe(201);
    expect(body).toMatchObject({ budget_usd: '25000', city: 'Київ', needed_when: 'asap' });
    await expect(page.getByTestId('lead-success')).toContainText('AFY-');
  });

  test('без згоди запит не йде, підказка біля чекбокса', async ({ page }) => {
    await calculate(page);
    await fillLead(page, { name: '[E2E] Без згоди', phone: '0671234567', consent: false });
    await expectNoRequest(page, LEADS_URL, async () => {
      await submitBtn(page).click();
    });
    await expect(page.getByText('Потрібна згода на обробку персональних даних.')).toBeVisible();
  });

  test('без згоди на передачу партнеру кнопка неактивна', async ({ page }) => {
    await calculate(page);
    await fillLead(page, { name: '[E2E] X', phone: '0671234567' });
    // Капча готова: кнопка активна, поки всі згоди стоять.
    await expect(submitBtn(page)).toBeEnabled();
    await page.getByTestId('lead-form').getByLabel(/передачу моїх контактних даних партнеру/).uncheck();
    await expect(submitBtn(page)).toBeDisabled();
  });

  test('текст згоди партнеру на екрані дослівно збігається з відповіддю site-settings', async ({ page, request }) => {
    const settings = await (await request.get('/api/v1/site-settings/')).json();
    expect(settings.partner_consent_text).toContain(settings.partner_name);
    await calculate(page);
    await expect(page.getByTestId('partner-consent-text')).toHaveText(settings.partner_consent_text);
  });

  test('порожній телефон: запиту немає, validity.valueMissing', async ({ page }) => {
    await calculate(page);
    await fillLead(page, { name: '[E2E] Без телефону' });
    const phone = page.getByTestId('lead-form').getByLabel('Телефон');
    expect(await phone.evaluate((el: HTMLInputElement) => el.validity.valueMissing)).toBe(true);
    await expect(phone).toHaveAttribute('type', 'tel');
    await expectNoRequest(page, LEADS_URL, async () => {
      await submitBtn(page).click();
    });
    await expect(page.getByText('Вкажіть телефон.')).toBeVisible();
  });

  test('телефон 12345 -> 400, текст під полем, не JSON', async ({ page }) => {
    await calculate(page);
    await fillLead(page, { name: '[E2E] Телефон', phone: '12345' });
    const { resp } = await submitAndWait(page);
    expect(resp.status()).toBe(400);
    await expect(page.getByText('Вкажіть номер у форматі +380XXXXXXXXX.')).toBeVisible();
    await expect(page.getByText('{"')).toHaveCount(0);
    await expect(page.getByTestId('lead-form')).toBeVisible();
  });

  test('429 -> «Забагато заявок»', async ({ page }) => {
    await page.route('**/api/v1/leads/', (r) => r.request().method() === 'POST'
      ? r.fulfill({ status: 429, json: { detail: 'throttled' } })
      : r.fallback());
    await calculate(page);
    await fillLead(page, { name: '[E2E] 429', phone: '0671234567' });
    await submitAndWait(page);
    await expect(page.getByText('Забагато заявок')).toBeVisible();
  });

  test('500 -> загальне повідомлення без сирого JSON', async ({ page }) => {
    await page.route('**/api/v1/leads/', (r) => r.request().method() === 'POST'
      ? r.fulfill({ status: 500, body: 'oops' })
      : r.fallback());
    await calculate(page);
    await fillLead(page, { name: '[E2E] 500', phone: '0671234567' });
    await submitAndWait(page);
    await expect(page.getByText('Не вдалося надіслати заявку')).toBeVisible();
  });

  test('Q2: Turnstile увімкнено, віджет не завантажився -> кнопка неактивна', async ({ page }) => {
    await page.route('**/api/v1/auth/config/', async (r) => {
      const real = await (await r.fetch()).json();
      await r.fulfill({ json: { ...real, captcha: { ...real.captcha, provider: 'turnstile', site_key: 'e2e-key' } } });
    });
    await page.route('https://challenges.cloudflare.com/**', (r) => r.abort());
    await calculate(page);
    await fillLead(page, { name: '[E2E] Turnstile', phone: '0671234567' });
    await expect(page.getByText('Не вдалося завантажити перевірку')).toBeVisible();
    await expect(submitBtn(page)).toBeDisabled();
  });

  test('Н-33: після 400 captcha_failed токен оновлюється', async ({ page }) => {
    let configCalls = 0;
    const tokens: unknown[] = [];
    await page.route('**/api/v1/auth/config/', async (r) => { configCalls += 1; await r.fallback(); });
    let failedOnce = false;
    await page.route('**/api/v1/leads/', async (r) => {
      if (r.request().method() !== 'POST') return r.fallback();
      tokens.push(r.request().postDataJSON().captcha_token);
      if (!failedOnce) {
        failedOnce = true;
        return r.fulfill({ status: 400, json: { code: 'captcha_failed', detail: 'Перевірку не пройдено' } });
      }
      return r.fallback();
    });
    await calculate(page);
    await fillLead(page, { name: '[E2E] Captcha', phone: '0671234567' });
    await submitAndWait(page);
    await expect(page.getByText('Не вдалося пройти перевірку')).toBeVisible();
    await expect.poll(() => configCalls).toBeGreaterThanOrEqual(2);
    const { resp } = await submitAndWait(page);
    expect(resp.status()).toBe(201);
    expect(tokens).toHaveLength(2);
    expect(tokens[1]).toBeTruthy();
    expect(tokens[1]).not.toBe(tokens[0]);
  });

  test('регрес 09-Q7: протухлий токен у cookie, гість лишається на /calculator і бачить успіх', async ({ page, context, baseURL }) => {
    await context.addCookies([
      { name: 'access', value: 'expired.invalid.token', url: baseURL! },
      { name: 'refresh', value: 'expired.invalid.token', url: baseURL! },
      { name: 'has_session', value: '1', url: baseURL! },
    ]);
    await page.addInitScript(() => {
      window.localStorage.setItem('access', 'expired.invalid.token');
      window.localStorage.setItem('refresh', 'expired.invalid.token');
    });
    await calculate(page);
    await fillLead(page, { name: '[E2E] Протухлий', phone: '0671234567' });
    await submitAndWait(page);
    await expect(page.getByTestId('lead-success')).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/calculator');
  });

  test('обхід: /me/leads для гостя веде на /login', async ({ page }) => {
    await page.goto('/me/leads');
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('Джерело заявки (Н-26)', () => {
  test('UTM зберігаються в sessionStorage, не в cookie, і йдуть у тілі запиту', async ({ page, context }) => {
    await page.goto('/calculator?utm_source=tiktok&utm_campaign=test');
    await page.goto('/listings');
    await calculate(page);
    await fillLead(page, { name: '[E2E] UTM', phone: '0671234567' });
    const { resp, body } = await submitAndWait(page);
    expect(resp.status()).toBe(201);
    expect(body.utm).toEqual({ source: 'tiktok', campaign: 'test' });
    expect(body.entry_page_url).toBe('/calculator');
    expect(body.page_url).toBe('/calculator');
    expect(await page.evaluate(() => window.sessionStorage.getItem('afy:attribution'))).toContain('tiktok');
    const cookies = await context.cookies();
    expect(JSON.stringify(cookies)).not.toContain('tiktok');
  });

  test('нова кампанія замінює стару; звичайний перехід не стирає', async ({ page }) => {
    await page.goto('/calculator?utm_source=tiktok&utm_campaign=a');
    await page.goto('/calculator?utm_source=instagram');
    await page.goto('/listings');
    await calculate(page);
    await fillLead(page, { name: '[E2E] UTM2', phone: '0671234567' });
    const { body } = await submitAndWait(page);
    expect(body.utm).toEqual({ source: 'instagram' });
  });

  test('UTM з недопустимими символами відкидаються, кирилиця проходить', async ({ page }) => {
    await page.goto('/calculator?utm_source=%3Cscript%3E&utm_campaign=%D0%B2%D0%B5%D1%81%D0%BD%D0%B0_1');
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await fillLead(page, { name: '[E2E] UTM3', phone: '0671234567' });
    const { body } = await submitAndWait(page);
    expect(body.utm).toEqual({ campaign: 'весна_1' });
  });

  test('page_url без query, реферер власного сайту ігнорується, зовнішній зберігається як origin', async ({ page, baseURL }) => {
    await page.goto('/calculator?utm_source=x&token=secret', { referer: `${baseURL}/listings` });
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await fillLead(page, { name: '[E2E] URL', phone: '0671234567' });
    const { body } = await submitAndWait(page);
    expect(body.page_url).toBe('/calculator');
    expect(body.referrer).toBeUndefined();
    expect(JSON.stringify(body)).not.toContain('secret');
  });

  test('зовнішній реферер потрапляє в тіло як origin', async ({ page }) => {
    await page.goto('/calculator', { referer: 'https://www.google.com/search?q=secret' });
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await fillLead(page, { name: '[E2E] Ref', phone: '0671234567' });
    const { body } = await submitAndWait(page);
    expect(body.referrer).toBe('https://www.google.com');
  });

  test('sessionStorage недоступний: сторінка працює, заявка без utm, 201', async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, 'sessionStorage', {
        get() { throw new DOMException('denied', 'SecurityError'); },
      });
    });
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto('/calculator?utm_source=tiktok');
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await fillLead(page, { name: '[E2E] NoStorage', phone: '0671234567' });
    const { resp, body } = await submitAndWait(page);
    expect(resp.status()).toBe(201);
    expect(body.utm).toBeUndefined();
    expect(errors).toEqual([]);
  });
});

test.describe('Лот', () => {
  test('кнопка «Залишити заявку» -> форма з listing_id -> успіх', async ({ page, request }) => {
    const list = await (await request.get('/api/v1/listings/?search=RAV4')).json();
    const item = (list.results as { id: number; vehicle_detail: { model: string } }[])
      .find((l) => l.vehicle_detail.model.includes('[E2E] RAV4 retail'));
    expect(item, 'e2e_seed: роздрібний лот [E2E]').toBeTruthy();
    await page.goto(`/listings/${item!.id}`);
    await page.getByRole('button', { name: 'Залишити заявку' }).click();
    await fillLead(page, { name: '[E2E] Лот', phone: '0671234567' });
    const { resp, body } = await submitAndWait(page);
    expect(resp.status()).toBe(201);
    expect(body).toMatchObject({ source: 'listing', listing_id: item!.id });
    await expect(page.getByTestId('lead-success')).toContainText('AFY-');
  });
});

test.describe('Покупець', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('поля передзаповнені з профілю; заявка видна в /me/leads зі статусом «Нова»', async ({ page, api }) => {
    const buyer = await api('buyer');
    const profile = await (await buyer.get('/api/v1/auth/profile/')).json();
    await calculate(page);
    const form = page.getByTestId('lead-form');
    const fullName = [profile.first_name, profile.last_name].filter(Boolean).join(' ');
    await expect(form.getByLabel("Ім'я")).toHaveValue(fullName);
    await expect(form.getByLabel('Телефон')).toHaveValue(profile.phone ?? '');
    await form.getByLabel("Ім'я").fill('[E2E] Покупець');
    await form.getByLabel('Телефон').fill('0671234567');
    await fillLead(page);
    const { resp } = await submitAndWait(page);
    expect(resp.status()).toBe(201);
    const publicId = ((await resp.json()) as { public_id: string }).public_id;

    await page.goto('/me/leads');
    const item = page.getByTestId('lead-item').filter({ hasText: publicId });
    await expect(item).toBeVisible();
    await expect(item.getByText('Нова', { exact: true })).toBeVisible();
  });

  test('Q2: заповнений honeypot -> 201, запису немає (/leads/mine/ до і після)', async ({ page, api }) => {
    const buyer = await api('buyer');
    const count = async () => (await (await buyer.get('/api/v1/leads/mine/')).json()).count as number;
    const before = await count();
    await calculate(page);
    await fillLead(page, { name: '[E2E] Бот', phone: '0671234567' });
    await page.locator('input[name="website"]').evaluate((el: HTMLInputElement) => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      set.call(el, 'http://spam.example');
      el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const { resp, body } = await submitAndWait(page);
    expect(body.website).toBe('http://spam.example');
    expect(resp.status()).toBe(201);
    expect(await count()).toBe(before);
  });

  test('помилка завантаження /me/leads — повідомлення, а не порожній список', async ({ page }) => {
    await page.route('**/api/v1/leads/mine/**', (r) => r.fulfill({ status: 500, body: 'x' }));
    await page.goto('/me/leads');
    await expect(page.getByText('Не вдалося завантажити заявки')).toBeVisible();
    await expect(page.getByText('Заявок ще немає')).toHaveCount(0);
  });

  test('порожній стан /me/leads', async ({ page }) => {
    await page.route('**/api/v1/leads/mine/**', (r) => r.fulfill({ json: { count: 0, next: null, previous: null, results: [] } }));
    await page.goto('/me/leads');
    await expect(page.getByText('Заявок ще немає')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Порахувати вартість' })).toBeVisible();
  });

  test('меню кабінету має «Мої заявки»', async ({ page }) => {
    await page.goto('/me');
    await page.getByRole('link', { name: /Мої заявки/ }).click();
    await expect(page).toHaveURL(/\/me\/leads/);
  });
});

test.describe('Партнер не налаштований', () => {
  test('порожній partner_name: чекбокс і кнопка неактивні', async ({ page }) => {
    await page.route('**/api/v1/site-settings/', async (r) => {
      const real = await (await r.fetch()).json();
      await r.fulfill({ json: { ...real, partner_name: '', partner_consent_text: '' } });
    });
    await calculate(page);
    await expect(page.getByText('партнера ще не налаштовано')).toBeVisible();
    // Капча готова (honeypot-токен віддається через ~3 с): тільки тоді «неактивна» не пояснюється очікуванням.
    await expect(page.locator('input[name="website"]')).toBeAttached(); // конфіг капчі отримано
    await page.waitForTimeout(3500); // одноразове очікування мінімального часу заповнення капчі
    await expect(page.getByTestId('lead-form').getByLabel(/передачу моїх контактних даних партнеру|Згода на передачу/)).toBeDisabled();
    await expect(submitBtn(page)).toBeDisabled();
  });
});
