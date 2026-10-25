/**
 * E2E: адаптери НБУ і пошти (задача 3.4a). Частина LiqPay/Telegram — задача 3.4b, тут її немає.
 * Сторінка статусу інтеграцій у Django Admin: /admin/integrations/status/.
 */
import { test, expect, storageStatePath } from './fixtures';

const STATUS_URL = '/admin/integrations/status/';
const BUTTON_URLS = [
  '/admin/integrations/status/refresh-nbu/',
  '/admin/integrations/status/test-email/',
];
const NOT_CONFIGURED = 'Відправка листів тимчасово не налаштована, зверніться до підтримки';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Адмінка: кнопки перевірки НБУ і пошти (3.4a)', () => {
  // Потрібен суперкористувач адмінки з правом integrations.view_integrationhealth, а e2e_seed його не створює
  // (staff@e2e.test — лише is_staff без прав). Знімати fixme після додавання такого користувача в e2e_seed.
  test.fixme('3.4a → e2e_seed без суперкористувача (як 3.1): «Надіслати тестовий лист» — повідомлення про успіх, лист у Mailpit або запис у Outbox', async ({ page }) => {
    await page.goto('/admin/login/?next=/admin/');
    await page.getByLabel(/email|користувач|username/i).fill('admin@e2e.test');
    await page.getByLabel(/пароль|password/i).fill(process.env.E2E_PASSWORD ?? '');
    await page.getByRole('button', { name: /увійти|log in/i }).click();
    await page.goto(STATUS_URL);
    await page.getByRole('button', { name: 'Надіслати тестовий лист' }).click();
    await expect(page.locator('.messagelist .success')).toBeVisible();
  });

  test.describe('звичайний користувач', () => {
    test.use({ storageState: storageStatePath('buyer') });

    test('обхід: сторінка статусу веде на вхід в адмінку, таблиці немає', async ({ page }) => {
      await page.goto(STATUS_URL);
      await expect(page).toHaveURL(/\/admin\/login\//);
      await expect(page.locator('#integrations-status-table')).toHaveCount(0);
    });

    for (const url of BUTTON_URLS) {
      test(`обхід: POST ${url} веде на вхід в адмінку, а не виконує дію`, async ({ page }) => {
        // Токен CSRF бере сторінка входу в адмінку: без нього Django відповів би 403 раніше за редірект.
        await page.goto('/admin/login/');
        const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? '';
        expect(csrf, 'сторінка входу в адмінку не віддала csrftoken').not.toBe('');
        const resp = await page.request.post(url, { headers: { 'X-CSRFToken': csrf }, maxRedirects: 0 });
        expect(resp.status()).toBe(302);
        expect(resp.headers()['location']).toMatch(/\/admin\/login\//);
      });
    }
  });
});

test.describe('Скидання пароля, пошта не налаштована (3.4a)', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('503 від API — на формі видно текст «Відправка листів тимчасово не налаштована», «надіслано» немає', async ({ page }) => {
    await page.route('**/api/v1/auth/password-reset/', (route) =>
      route.fulfill({ status: 503, json: { detail: NOT_CONFIGURED, configured: false } }),
    );
    await page.goto('/password-reset');
    await page.getByLabel('Email').fill('nobody@e2e.test');
    const submit = page.getByRole('button', { name: 'Надіслати посилання' });
    await expect(submit).toBeEnabled();
    const answered = page.waitForResponse((r) =>
      r.url().includes('/api/v1/auth/password-reset/') && r.request().method() === 'POST');
    await submit.click();
    expect((await answered).status()).toBe(503);
    await expect(page.getByTestId('form-error')).toHaveText(NOT_CONFIGURED);
    await expect(page.getByTestId('reset-sent')).toHaveCount(0);
  });
});

test.describe('Калькулятор: демо-курс (3.4a, 02-C8)', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('курс із сида має джерело demo, і демо-банер показаний', async ({ page }) => {
    // Механізм 2.6 виводить в UI лише DemoBanner за is_demo; окремого поля джерела курсу в UI немає,
    // тож джерело перевіряємо у відповіді API, а банер — на сторінці.
    await page.goto('/calculator');
    const answered = page.waitForResponse((r) =>
      r.url().includes('/api/v1/pricing/calculate/') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    const resp = await answered;
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body.exchange_rate_source).toBe('demo');
    expect(body.is_demo).toBe(true);
    await expect(page.getByTestId('calc-result')).toBeVisible();
    await expect(page.getByTestId('demo-banner').first()).toBeVisible();
  });
});
