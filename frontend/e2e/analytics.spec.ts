/**
 * E2E: аналітика GA4 і Cloudflare Web Analytics (задача 3.5, 🔒).
 *
 * ID у e2e-стеку не задані, тому публічні налаштування підміняються через page.route (поле analytics),
 * а скрипти провайдерів — заглушками: у мережу тести не ходять. Набір ID на клієнті, а CSP стенду
 * зібрана без доменів аналітики (вони додаються лише за заданих ID у .env) і не пустила б заглушки,
 * тому CSP вимкнено. Домени в CSP за наявності ID перевіряє крок CI «nginx -t for every TLS_MODE».
 * Тестові ID навмисно не схожі на справжні ключі (gitleaks).
 */
import type { Page, Request } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

test.use({ storageState: { cookies: [], origins: [] }, bypassCSP: true });

const GA_ID = 'G-TEST000000';
const CF_TOKEN = 'CFTEST0000000000';
const BANNER = 'Налаштування файлів cookie';

const isGa = (r: Request) => /googletagmanager\.com|google-analytics\.com/.test(r.url());
const isCf = (r: Request) => /cloudflareinsights\.com/.test(r.url());

type Analytics = { ga4_id?: string; cloudflare_token?: string };

async function mockProviders(
  page: Page,
  opts: { analytics: Analytics; blockScripts?: boolean; settings?: Record<string, unknown> },
) {
  await page.route('**/api/v1/site-settings/', async (route) => {
    const resp = await route.fetch();
    const json = await resp.json();
    await route.fulfill({ response: resp, json: { ...json, ...opts.settings, analytics: opts.analytics } });
  });
  for (const pattern of ['**/googletagmanager.com/**', '**/static.cloudflareinsights.com/**']) {
    await page.route(pattern, (route) =>
      opts.blockScripts
        ? route.abort()
        : route.fulfill({ contentType: 'application/javascript', body: '/* stub */' }));
  }
}

const choose = (page: Page, name: 'Лише необхідні' | 'Прийняти всі') =>
  page.getByRole('dialog', { name: BANNER }).getByRole('button', { name }).click();

const dataLayer = (page: Page) =>
  page.evaluate(() => JSON.stringify(((window as unknown as { dataLayer?: unknown[] }).dataLayer ?? []).map((e) => Array.from(e as ArrayLike<unknown>))));

const gaScripts = (page: Page) => page.locator('script[src*="googletagmanager.com"]');

async function calculate(page: Page) {
  await page.goto('/calculator');
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  await expect(page.getByRole('heading', { name: 'Залишити заявку брокеру' })).toBeVisible();
}

test.describe('GA4: тільки після згоди', () => {
  test('до вибору і після «Лише необхідні» запитів і скриптів GA немає', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: GA_ID } });
    await expectNoRequest(page, isGa, async () => {
      await page.goto('/');
      await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
      await expect(gaScripts(page)).toHaveCount(0);
      await choose(page, 'Лише необхідні');
      await expect(page.getByRole('dialog', { name: BANNER })).toBeHidden();
    });
    await expect(gaScripts(page)).toHaveCount(0);
    expect(await page.evaluate(() => typeof (window as unknown as { gtag?: unknown }).gtag)).toBe('undefined');
  });

  test('«Прийняти всі»: скрипт запитано, подія generate_lead із source без ПДн', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: GA_ID } });
    await page.goto('/');
    const scriptReq = page.waitForRequest((r) => r.url().includes('googletagmanager.com/gtag/js'));
    await choose(page, 'Прийняти всі');
    expect((await scriptReq).url()).toContain(`id=${GA_ID}`);
    await expect(gaScripts(page)).toHaveCount(1);

    await calculate(page);
    expect(await dataLayer(page)).toContain('calculator_calculate');

    const form = page.getByTestId('lead-form');
    await form.getByLabel("Ім'я").fill('[E2E] Аналітика');
    await form.getByLabel('Телефон').fill('067 765 43 21');
    await form.getByLabel('Email').fill('analytics@e2e.test');
    await form.getByLabel(/обробку персональних даних/).check();
    await form.getByLabel(/передачу моїх контактних даних партнеру/).check();
    await form.getByRole('button', { name: 'Надіслати' }).click();
    await expect(page.getByTestId('lead-success')).toBeVisible();

    const layer = await dataLayer(page);
    expect(layer).toContain('generate_lead');
    expect(layer).toContain('"source":"calculator"');
    for (const secret of ['Аналітика', '067', '765', 'analytics@e2e.test']) expect(layer).not.toContain(secret);
  });

  test('відкликання згоди на /cookies: cookie _ga видалено, відправка вимкнена, події не йдуть', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: GA_ID } });
    await page.goto('/');
    await choose(page, 'Прийняти всі');
    await expect(gaScripts(page)).toHaveCount(1);
    await page.evaluate(() => { document.cookie = '_ga=GA1.1.1.1; path=/'; document.cookie = '_ga_TEST=GS1; path=/'; });

    await page.goto('/cookies');
    await expect(gaScripts(page)).toHaveCount(1);
    await page.getByRole('button', { name: 'Відкликати згоду' }).click();

    await expect(gaScripts(page)).toHaveCount(0);
    // Consent Mode: GA повідомлено, що зберігання заборонено.
    expect(await dataLayer(page)).toContain('"analytics_storage":"denied"');
    expect(await page.evaluate(() => document.cookie)).not.toMatch(/_ga/);
    expect(await page.evaluate((id) => (window as unknown as Record<string, unknown>)[`ga-disable-${id}`], GA_ID)).toBe(true);

    await calculate(page);
    expect(await dataLayer(page)).toBe('[]');
    await expect(gaScripts(page)).toHaveCount(0);
  });

  test('стара згода «all» при новій версії документів і reconsent: GA не стартує (гонка запитів)', async ({ page }) => {
    await mockProviders(page, {
      analytics: { ga4_id: GA_ID },
      settings: { legal_docs_version: 'new', legal_docs_reconsent_required: true },
    });
    await page.addInitScript(() =>
      window.localStorage.setItem('cookie_consent', JSON.stringify({ level: 'all', version: 'old', ts: null })));
    await expectNoRequest(page, isGa, async () => {
      await page.goto('/');
      await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
    });
    await expect(gaScripts(page)).toHaveCount(0);
  });

  test('адреса в GA без query: page_location і page_referrer не містять «?» і токенів', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: GA_ID } });
    await page.goto('/');
    await choose(page, 'Прийняти всі');
    await expect(gaScripts(page)).toHaveCount(1);
    await page.goto('/calculator?conv=SECRETQ&q=SECRETSEARCH');
    await expect(page.getByRole('button', { name: 'Розрахувати' })).toBeVisible();
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await expect(page.getByRole('heading', { name: 'Залишити заявку брокеру' })).toBeVisible();
    const layer = await dataLayer(page);
    const locations = [...layer.matchAll(/"page_(?:location|referrer)":"([^"]*)"/g)].map((m) => m[1]);
    expect(locations.length).toBeGreaterThan(0);
    for (const l of locations) expect(l).not.toContain('?');
    expect(layer).not.toContain('SECRET');
    expect(layer).toContain('"page_view"');
  });

  test('/verify-email: токен прибрано з адреси й не потрапляє в GA', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: GA_ID } });
    await page.goto('/');
    await choose(page, 'Прийняти всі');
    await page.goto('/verify-email?uid=abc&token=SECRETTOK');
    await expect(page).toHaveURL(/\/verify-email$/);
    await expect(gaScripts(page)).toHaveCount(1);
    expect(await dataLayer(page)).not.toContain('SECRETTOK');
  });

  test('перемикання «Прийняти всі» → «Лише необхідні» на /cookies вивантажує GA', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: GA_ID } });
    await page.goto('/');
    await choose(page, 'Прийняти всі');
    await expect(gaScripts(page)).toHaveCount(1);
    await page.evaluate(() => { document.cookie = '_ga=GA1.1.1.1; path=/'; });
    await page.goto('/cookies');
    await expect(gaScripts(page)).toHaveCount(1);
    await page.getByRole('button', { name: 'Лише необхідні' }).click();
    await expect(gaScripts(page)).toHaveCount(0);
    expect(await page.evaluate(() => document.cookie)).not.toMatch(/_ga/);
    expect(await page.evaluate((id) => (window as unknown as Record<string, unknown>)[`ga-disable-${id}`], GA_ID)).toBe(true);
    // Повторна згода в тій самій вкладці: вимірювання повертається без перезавантаження.
    await page.getByRole('button', { name: 'Прийняти всі' }).click();
    expect(await page.evaluate((id) => (window as unknown as Record<string, unknown>)[`ga-disable-${id}`], GA_ID)).toBe(false);
    expect(await dataLayer(page)).toContain('"analytics_storage":"granted"');
  });

  test('пошкоджене cookie_consent = «не вибрано», GA не стартує', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: GA_ID } });
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', '{"level":"all"'));
    await expectNoRequest(page, isGa, async () => {
      await page.goto('/');
      await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
    });
    await expect(gaScripts(page)).toHaveCount(0);
  });

  test('усі ID порожні + «Прийняти всі»: нічого не завантажується, помилок у консолі немає', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    await mockProviders(page, { analytics: {} });
    await expectNoRequest(page, (r) => isGa(r) || isCf(r), async () => {
      await page.goto('/');
      await choose(page, 'Прийняти всі');
      await expect(page.getByRole('dialog', { name: BANNER })).toBeHidden();
    });
    await expect(page.locator('script[data-afy-analytics]')).toHaveCount(0);
    expect(errors.filter((e) => !/Failed to load resource/.test(e))).toEqual([]);
  });

  test('ID недопустимого формату: провайдер вимкнено, нічого не вставлено', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: 'G-"><script>', cloudflare_token: 'bad token"' } });
    await expectNoRequest(page, (r) => isGa(r) || isCf(r), async () => {
      await page.goto('/');
      await choose(page, 'Прийняти всі');
      await expect(page.getByRole('dialog', { name: BANNER })).toBeHidden();
    });
    await expect(page.locator('script[data-afy-analytics]')).toHaveCount(0);
  });

  test('скрипт GA заблоковано: калькулятор і заявка працюють', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));
    await mockProviders(page, { analytics: { ga4_id: GA_ID }, blockScripts: true });
    await page.goto('/');
    await choose(page, 'Прийняти всі');
    await calculate(page);
    await expect(page.getByText('Сума орієнтовна')).toBeVisible();
    expect(pageErrors).toEqual([]);
  });
});

test.describe('Cloudflare Web Analytics: без cookie й без згоди', () => {
  test('скрипт вантажиться до вибору, завантажувач сам cookie не ставить, GA не чіпає', async ({ page, context }) => {
    await mockProviders(page, { analytics: { cloudflare_token: CF_TOKEN } });
    const cfReq = page.waitForRequest((r) => r.url().includes('static.cloudflareinsights.com/beacon.min.js'));
    await expectNoRequest(page, isGa, async () => {
      await page.goto('/');
      await cfReq;
      await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
    });
    await expect(page.locator('script[data-cf-beacon]')).toHaveAttribute('data-cf-beacon', `{"token":"${CF_TOKEN}"}`);
    const names = (await context.cookies()).map((c) => c.name);
    expect(names.filter((n) => n.startsWith('_ga') || n.startsWith('__cf'))).toEqual([]);
  });

  test('токен порожній: запитів до Cloudflare немає', async ({ page }) => {
    await mockProviders(page, { analytics: { ga4_id: GA_ID } });
    await expectNoRequest(page, isCf, async () => {
      await page.goto('/');
      await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
    });
  });
});
