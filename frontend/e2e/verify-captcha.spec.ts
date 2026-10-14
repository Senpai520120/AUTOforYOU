/**
 * E2E: підтвердження email і капча (задача 1.6, 23-P12 + блок «скидання віджета і блокування скрипта»).
 *
 * e2e-стек без ключів Turnstile: діє honeypot (форм-токен з /auth/config/). Сценарії Turnstile
 * (скидання віджета, заблокований скрипт) йдуть через page.route: підміна /auth/config/ на
 * provider=turnstile і підміна скрипта challenges.cloudflare.com.
 * Mailpit в e2e-стеку немає (EMAIL_BACKEND=console), тож сценарії «лист → посилання» — test.fixme.
 */
import type { Page, Route } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';
import { registerViaApi, captchaToken } from './helpers/captcha';

test.use({ storageState: { cookies: [], origins: [] } });

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

const isRegisterPost = (r: { url(): string; method(): string }) =>
  r.url().includes('/auth/register/') && r.method() === 'POST';

const TURNSTILE_CONFIG = {
  captcha: {
    provider: 'turnstile',
    site_key: '1x00000000000000000000AA', // публічний тестовий ключ Cloudflare
    login_after_failures: 3,
    on_login: false,
  },
  email_verification_required: true,
};

// Підміна скрипта Turnstile: кожен render/reset видає новий токен tok-N; __expire() імітує протухання.
const FAKE_TURNSTILE = `
(function () {
  var n = 0, widgets = {}, count = 0;
  window.turnstile = {
    render: function (el, o) {
      var id = 'w' + (++count); widgets[id] = o;
      setTimeout(function () { o.callback('tok-' + (++n)); }, 50);
      return id;
    },
    reset: function (id) { var o = widgets[id]; setTimeout(function () { o.callback('tok-' + (++n)); }, 50); },
    remove: function () {}
  };
  window.__expire = function () { Object.keys(widgets).forEach(function (k) { widgets[k]['expired-callback'](); }); };
})();
`;

async function mockTurnstileConfig(page: Page) {
  await page.route('**/api/v1/auth/config/', (route: Route) =>
    route.fulfill({ json: TURNSTILE_CONFIG, headers: { 'Cache-Control': 'no-store' } }));
}

async function fillRegisterForm(page: Page, email: string) {
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').first().fill('StrongPass123!');
  await page.locator('input[type="password"]').nth(1).fill('StrongPass123!');
  await page.getByLabel(/Погоджуюсь з/).check();
  await page.getByLabel(/18 років/).check();
}

test.describe('Підтвердження email (23-P12)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test.fixme('P12-1 успіх: реєстрація → лист із Mailpit → посилання → «Email підтверджено» → без банера → оголошення створюється → в e2e-стеку немає Mailpit (EMAIL_BACKEND=console), потрібне додати mail-catcher у docker-compose.e2e.yml', async () => {});

  test.fixme('P12-2 повторний перехід за тим самим посиланням показує помилку → потрібен Mailpit в e2e-стеку (див. P12-1)', async () => {});

  test('P12-3 неверифікований: банер у /me, 403 на заявці дилера з «Надіслати лист ще раз», лист надсилається повторно', async ({
    page,
    request,
    uniqueEmail,
  }) => {
    test.setTimeout(90_000);
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);

    await page.goto('/login');
    await page.locator('input[type="email"]').fill(uniqueEmail);
    await page.locator('input[type="password"]').fill(password);
    await page.getByRole('button', { name: 'Увійти' }).click();
    await expect(page).toHaveURL(/\/me$/);

    const banner = page.getByTestId('verify-email-banner');
    await expect(banner.getByText('Підтвердіть email', { exact: true })).toBeVisible();

    // Заявка дилера: сервер відповідає 403 email_not_verified, форма показує підказку.
    await page.goto('/dealers/apply');
    await page.getByPlaceholder('ТОВ Авто Трейд').fill('[E2E] Авто Трейд');
    await page.getByPlaceholder('Іван Петрович Іванов').fill('[E2E] Іван Іванов');
    await page.getByPlaceholder('+380991234567').fill('+380991234567');
    await page.getByLabel(/Я даю згоду на обробку/).check();
    const applyResponse = page.waitForResponse(
      (r) => r.url().includes('/dealers/apply/') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Подати заявку' }).click();
    const resp = await applyResponse;
    expect(resp.status()).toBe(403);
    expect((await resp.json()).code).toBe('email_not_verified');
    await expect(page.getByText(/Підтвердіть email, щоб виконати цю дію/)).toBeVisible();

    // Повторна відправка листа з банера в /me.
    await page.goto('/me');
    const resendResponse = page.waitForResponse(
      (r) => r.url().includes('/auth/verify-email/resend/') && r.request().method() === 'POST',
    );
    await page.getByTestId('verify-email-banner').getByRole('button', { name: 'Надіслати ще раз' }).click();
    expect((await resendResponse).status()).toBe(200);
    await expect(page.getByText('Лист надіслано. Перевірте пошту.')).toBeVisible();
  });

  test('P12-4 /verify-email з хибним токеном показує помилку', async ({ page }) => {
    await page.goto('/verify-email?uid=abc&token=wrong-token');
    await expect(page.getByRole('heading', { name: 'Не вдалося підтвердити email' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Email підтверджено' })).toHaveCount(0);
  });

  test('P12-5 /verify-email без параметрів показує помилку без запиту', async ({ page }) => {
    await expectNoRequest(
      page,
      (r) => r.url().includes('/auth/verify-email/'),
      async () => {
        await page.goto('/verify-email');
        await expect(page.getByRole('heading', { name: 'Не вдалося підтвердити email' })).toBeVisible();
      },
    );
  });
});

test.describe('Капча: обхід і сервер (23-P12)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('без чекбокса 18+ сервер відхиляє реєстрацію (400, is_adult), відповідь показана на API', async ({
    request,
    uniqueEmail,
  }) => {
    const password = e2ePassword();
    const resp = await request.post('/api/v1/auth/register/', {
      data: {
        email: uniqueEmail, password, password2: password, agreed_to_terms: true,
        is_adult: false, captcha_token: await captchaToken(request),
      },
    });
    expect(resp.status()).toBe(400);
    expect(Object.keys(await resp.json())).toContain('is_adult');
  });

  test('заповнене honeypot-поле → 400 captcha_failed', async ({ request, uniqueEmail }) => {
    const password = e2ePassword();
    const resp = await request.post('/api/v1/auth/register/', {
      data: {
        email: uniqueEmail, password, password2: password, agreed_to_terms: true,
        is_adult: true, website: 'http://spam.example', captcha_token: await captchaToken(request),
      },
    });
    expect(resp.status()).toBe(400);
    expect((await resp.json()).code).toBe('captcha_failed');
  });

  test('без токена капчі сервер відхиляє реєстрацію (400 captcha_failed)', async ({ request, uniqueEmail }) => {
    const password = e2ePassword();
    const resp = await request.post('/api/v1/auth/register/', {
      data: { email: uniqueEmail, password, password2: password, agreed_to_terms: true, is_adult: true },
    });
    expect(resp.status()).toBe(400);
    expect((await resp.json()).code).toBe('captcha_failed');
  });

  test('форма: кнопка неактивна, доки немає токена капчі, і запит не йде', async ({ page, uniqueEmail }) => {
    // Скрипт Turnstile підмінено на такий, що ніколи не віддає токен.
    await mockTurnstileConfig(page);
    await page.route('**/challenges.cloudflare.com/**', (route) =>
      route.fulfill({
        contentType: 'application/javascript',
        body: 'window.turnstile={render:function(){return "w1"},reset:function(){},remove:function(){}};',
      }));
    await page.goto('/register');
    await fillRegisterForm(page, uniqueEmail);

    const submit = page.getByRole('button', { name: 'Зареєструватися' });
    await expect(submit).toBeDisabled();
    await expectNoRequest(page, isRegisterPost, async () => {
      await submit.click({ force: true });
    });
    await expect(page).toHaveURL(/\/register/);
  });
});

test.describe('Капча: скидання віджета і блокування скрипта (Н-33)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
    await mockTurnstileConfig(page);
  });

  test('скрипт Turnstile заблоковано → повідомлення, кнопка неактивна, запит не йде', async ({ page, uniqueEmail }) => {
    await page.route('**/challenges.cloudflare.com/**', (route) => route.abort());
    await page.goto('/register');
    await fillRegisterForm(page, uniqueEmail);

    await expect(
      page.getByText('Не вдалося завантажити перевірку. Вимкніть блокувальник або спробуйте пізніше'),
    ).toBeVisible();
    const submit = page.getByRole('button', { name: 'Зареєструватися' });
    await expect(submit).toBeDisabled();
    await expectNoRequest(page, isRegisterPost, async () => {
      await submit.click({ force: true });
    });
  });

  test('після кожної відповіді сервера (і помилки) віджет скидається, друга відправка з новим токеном', async ({
    page,
    uniqueEmail,
  }) => {
    await page.route('**/challenges.cloudflare.com/**', (route) =>
      route.fulfill({ contentType: 'application/javascript', body: FAKE_TURNSTILE }));
    const sentTokens: string[] = [];
    await page.route('**/api/v1/auth/register/', async (route) => {
      sentTokens.push((route.request().postDataJSON() as { captcha_token?: string }).captcha_token ?? '');
      await route.fulfill({
        status: 400,
        json: { code: 'captcha_failed', captcha_token: ['Перевірку не пройдено.'] },
      });
    });

    await page.goto('/register');
    await fillRegisterForm(page, uniqueEmail);
    const submit = page.getByRole('button', { name: 'Зареєструватися' });

    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(page.getByText('Перевірку не пройдено.')).toBeVisible();
    expect(sentTokens).toEqual(['tok-1']);

    // Після відповіді сервера віджет скинуто: токен новий, кнопка знову активна.
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect.poll(() => sentTokens).toEqual(['tok-1', 'tok-2']);
  });

  test('токен протух (expired-callback) → кнопка знову неактивна', async ({ page, uniqueEmail }) => {
    await page.route('**/challenges.cloudflare.com/**', (route) =>
      route.fulfill({ contentType: 'application/javascript', body: FAKE_TURNSTILE }));
    await page.goto('/register');
    await fillRegisterForm(page, uniqueEmail);
    const submit = page.getByRole('button', { name: 'Зареєструватися' });
    await expect(submit).toBeEnabled();

    await page.evaluate(() => (window as unknown as { __expire: () => void }).__expire());
    await expect(submit).toBeDisabled();
  });
});
