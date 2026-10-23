/**
 * E2E: скидання і зміна пароля, вихід на всіх пристроях (задача 1.7, 23-P10, 23-P11).
 *
 * Листи перехоплює Mailpit e2e-стека (HTTP API на MAILPIT_URL, за замовчуванням http://localhost:8025).
 * У стеку немає ключів Turnstile, тож діє honeypot (форм-токен з /auth/config/).
 */
import type { APIRequestContext, Browser, Page, Route } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';
import { captchaToken, registerViaApi } from './helpers/captcha';

test.use({ storageState: { cookies: [], origins: [] } });

const MAILPIT = process.env.MAILPIT_URL ?? 'http://localhost:8025';
const NEW_PASSWORD = 'Nova-Parol-8472!';
const THIRD_PASSWORD = 'Tretij-Parol-5193!';

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

async function mailCount(request: APIRequestContext, to: string): Promise<number> {
  const resp = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:"${to}" subject:"скидання пароля"` } });
  expect(resp.status()).toBe(200);
  return ((await resp.json()) as { messages_count: number }).messages_count;
}

/** Чекає лист для адреси й повертає параметри посилання зі скидання пароля. */
async function resetLink(request: APIRequestContext, to: string): Promise<string> {
  let id = '';
  await expect.poll(async () => {
    const resp = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:"${to}" subject:"скидання пароля"` } });
    const body = (await resp.json()) as { messages: { ID: string }[] };
    id = body.messages[0]?.ID ?? '';
    return id;
  }, { message: 'лист скидання пароля не надійшов у Mailpit', timeout: 20_000 }).not.toBe('');
  const message = (await (await request.get(`${MAILPIT}/api/v1/message/${id}`)).json()) as { Text: string };
  const match = message.Text.match(/(https?:\/\/\S+\/password-reset\/confirm\?uid=\S+&token=\S+)/);
  expect(match, 'у листі немає посилання скидання').not.toBeNull();
  return new URL(match![1]).pathname + new URL(match![1]).search;
}

async function uiLogin(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole('button', { name: 'Увійти' }).click();
}

async function newContextPage(browser: Browser) {
  const context = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  await context.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  return { context, page: await context.newPage() };
}

async function fillNewPassword(page: Page, password: string) {
  await page.getByLabel('Новий пароль', { exact: true }).fill(password);
  await page.getByLabel('Повторіть пароль').fill(password);
  await page.getByRole('button', { name: 'Змінити пароль' }).click();
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Скидання пароля (23-P10)', () => {
  test('успіх: «Забули пароль?» → email → лист → посилання → новий пароль → вхід', async ({
    page, request, uniqueEmail,
  }) => {
    test.setTimeout(120_000);
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);

    await page.goto('/login');
    await page.getByRole('link', { name: 'Забули пароль?' }).click();
    await expect(page).toHaveURL(/\/password-reset$/);
    await page.getByLabel('Email').fill(uniqueEmail);
    const submit = page.getByRole('button', { name: 'Надіслати посилання' });
    await expect(submit).toBeEnabled(); // honeypot-токен дозріває ~3 с
    await submit.click();
    await expect(page.getByTestId('reset-sent')).toContainText('Якщо акаунт із такою адресою існує');

    const link = await resetLink(request, uniqueEmail);
    await page.goto(link);
    await fillNewPassword(page, NEW_PASSWORD);
    await expect(page.getByTestId('reset-done')).toBeVisible();

    // Старий пароль більше не діє, новий — діє.
    await uiLogin(page, uniqueEmail, password);
    await expect(page.getByText('Невірний email або пароль')).toBeVisible();
    await page.locator('input[type="password"]').fill(NEW_PASSWORD);
    await page.getByRole('button', { name: 'Увійти' }).click();
    await expect(page).toHaveURL(/\/me$/);
  });

  test('відповідь однакова для чужого email; листа немає', async ({ page, request, uniqueEmail }) => {
    await page.goto('/password-reset');
    await page.getByLabel('Email').fill(uniqueEmail); // акаунта з цією адресою немає
    const submit = page.getByRole('button', { name: 'Надіслати посилання' });
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(page.getByTestId('reset-sent')).toContainText('Якщо акаунт із такою адресою існує');
    // Листа для неіснуючого акаунта немає (позитивний контроль із листом — у тесті обходу капчі).
    expect(await mailCount(request, uniqueEmail)).toBe(0);
  });

  test('помилка/обхід: повторне відкриття того ж посилання і зіпсований токен — зрозумілий текст, пароль не змінюється', async ({
    page, request, uniqueEmail,
  }) => {
    test.setTimeout(120_000);
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    await page.goto('/password-reset');
    await page.getByLabel('Email').fill(uniqueEmail);
    const submit = page.getByRole('button', { name: 'Надіслати посилання' });
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(page.getByTestId('reset-sent')).toBeVisible();
    const link = await resetLink(request, uniqueEmail);

    // Зіпсований токен.
    await page.goto(`${link}x`);
    await fillNewPassword(page, THIRD_PASSWORD);
    await expect(page.getByTestId('form-error')).toContainText('Посилання недійсне або термін його дії минув.');

    // Слабкий пароль з чинним токеном: текст помилки валідатора, токен лишається чинним.
    await page.goto(link);
    // Токен прибрано з адреси після завантаження; заголовок Referrer-Policy стоїть.
    await expect(page).toHaveURL(/\/password-reset\/confirm$/);
    expect(page.url()).not.toContain('token');
    await fillNewPassword(page, '12345678');
    await expect(page.getByTestId('form-error')).toBeVisible();
    await expect(page.getByTestId('reset-done')).toHaveCount(0);

    // Успішна зміна, потім повторне відкриття того ж посилання.
    await page.goto(link);
    await fillNewPassword(page, NEW_PASSWORD);
    await expect(page.getByTestId('reset-done')).toBeVisible();
    await page.goto(link);
    await fillNewPassword(page, THIRD_PASSWORD);
    await expect(page.getByTestId('form-error')).toContainText('Посилання недійсне або термін його дії минув.');

    // Пароль лишився NEW_PASSWORD, а не THIRD_PASSWORD.
    await uiLogin(page, uniqueEmail, THIRD_PASSWORD);
    await expect(page.getByText('Невірний email або пароль')).toBeVisible();
    await page.locator('input[type="password"]').fill(NEW_PASSWORD);
    await page.getByRole('button', { name: 'Увійти' }).click();
    await expect(page).toHaveURL(/\/me$/);
  });

  test('Referrer-Policy: no-referrer на сторінках скидання', async ({ request }) => {
    for (const path of ['/password-reset', '/password-reset/confirm']) {
      const resp = await request.get(path);
      expect(resp.headers()['referrer-policy'], path).toBe('no-referrer');
    }
  });

  test('сторінка confirm без параметрів: повідомлення, запиту немає', async ({ page }) => {
    await expectNoRequest(
      page,
      (r) => r.url().includes('/password-reset/confirm/'),
      async () => {
        await page.goto('/password-reset/confirm');
        await expect(page.getByText('Посилання недійсне або термін його дії минув.')).toBeVisible();
      },
    );
  });

  test('капча: віджет видно; без токена кнопка неактивна і запит не йде', async ({ page, uniqueEmail }) => {
    await page.route('**/api/v1/auth/config/', (route: Route) =>
      route.fulfill({
        json: {
          captcha: { provider: 'turnstile', site_key: '1x00000000000000000000AA', login_after_failures: 3, on_login: false },
          email_verification_required: true,
        },
        headers: { 'Cache-Control': 'no-store' },
      }));
    // Скрипт Turnstile, що ніколи не віддає токен.
    await page.route('**/challenges.cloudflare.com/**', (route) =>
      route.fulfill({
        contentType: 'application/javascript',
        body: 'window.turnstile={render:function(){return "w1"},reset:function(){},remove:function(){}};',
      }));
    await page.goto('/password-reset');
    await page.getByLabel('Email').fill(uniqueEmail);
    await expect(page.getByTestId('captcha-widget')).toBeAttached();
    const submit = page.getByRole('button', { name: 'Надіслати посилання' });
    await expect(submit).toBeDisabled();
    await expectNoRequest(
      page,
      (r) => r.url().includes('/auth/password-reset/') && r.method() === 'POST',
      async () => { await submit.click({ force: true }); },
    );
  });

  test('обхід капчі: прямий POST без токена → 400 captcha_failed, листа немає', async ({ request, uniqueEmail }) => {
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    const denied = await request.post('/api/v1/auth/password-reset/', { data: { email: uniqueEmail } });
    expect(denied.status()).toBe(400);
    expect((await denied.json()).code).toBe('captcha_failed');

    const ok = await request.post('/api/v1/auth/password-reset/', {
      data: { email: uniqueEmail, captcha_token: await captchaToken(request) },
    });
    expect(ok.status()).toBe(200);
    await resetLink(request, uniqueEmail);
    expect(await mailCount(request, uniqueEmail)).toBe(1); // лист один — від другого запиту
  });

  test.fixme('P10-turnstile: з тестовим ключем Turnstile віджет проходить, лист приходить → потрібен вихід у мережу до challenges.cloudflare.com (тестові ключі 1x000…AA/1x000…AA секрет)', async () => {});
});

test.describe('Зміна пароля і сесії (23-P11)', () => {
  test('успіх: зміна в /me/security, інший пристрій виходить, вхід з новим паролем', async ({
    page, browser, request, uniqueEmail,
  }) => {
    test.setTimeout(120_000);
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);

    // Другий пристрій входить першим: його сесія має бути відкликана зміною пароля.
    const second = await newContextPage(browser);
    try {
      await uiLogin(second.page, uniqueEmail, password);
      await expect(second.page).toHaveURL(/\/me$/);

      await uiLogin(page, uniqueEmail, password);
      await expect(page).toHaveURL(/\/me$/);
      await page.getByRole('link', { name: /Безпека/ }).click();
      await expect(page).toHaveURL(/\/me\/security$/);

      await page.getByLabel('Поточний пароль').fill(password);
      await page.getByLabel('Новий пароль', { exact: true }).fill(NEW_PASSWORD);
      await page.getByLabel('Повторіть новий пароль').fill(NEW_PASSWORD);
      await page.getByRole('button', { name: 'Змінити пароль' }).click();
      await expect(page.getByRole('status')).toContainText('Пароль змінено, інші пристрої вийшли з акаунту');

      // Поточний пристрій лишається в системі (нова пара cookie).
      await page.goto('/me');
      await expect(page).toHaveURL(/\/me$/);
      await expect(page.getByText(uniqueEmail).first()).toBeVisible();

      // Другий пристрій викинуто на /login.
      await second.page.goto('/me');
      await expect(second.page).toHaveURL(/\/login/);
    } finally {
      await second.context.close();
    }

    // Вхід новим паролем.
    await page.context().clearCookies();
    await uiLogin(page, uniqueEmail, NEW_PASSWORD);
    await expect(page).toHaveURL(/\/me$/);
  });

  test('помилка: неправильний поточний пароль — текст помилки, пароль не змінюється', async ({
    page, request, uniqueEmail,
  }) => {
    test.setTimeout(90_000);
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    await uiLogin(page, uniqueEmail, password);
    await expect(page).toHaveURL(/\/me$/);
    await page.goto('/me/security');
    await page.getByLabel('Поточний пароль').fill('Zovsim-Inshij-1234!');
    await page.getByLabel('Новий пароль', { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel('Повторіть новий пароль').fill(NEW_PASSWORD);
    await page.getByRole('button', { name: 'Змінити пароль' }).click();
    await expect(page.getByTestId('form-error')).toContainText('Поточний пароль невірний.');
    await expect(page.getByText('Пароль змінено, інші пристрої вийшли з акаунту')).toHaveCount(0);

    await page.context().clearCookies();
    await uiLogin(page, uniqueEmail, password); // старий пароль досі чинний
    await expect(page).toHaveURL(/\/me$/);
  });

  test('«Вийти на всіх пристроях»: поточний і інший пристрій на /login', async ({
    page, browser, request, uniqueEmail,
  }) => {
    test.setTimeout(120_000);
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    const second = await newContextPage(browser);
    try {
      await uiLogin(second.page, uniqueEmail, password);
      await expect(second.page).toHaveURL(/\/me$/);

      await uiLogin(page, uniqueEmail, password);
      await expect(page).toHaveURL(/\/me$/);
      await page.goto('/me/security');
      await page.getByRole('button', { name: 'Вийти на всіх пристроях' }).click();
      await expect(page).toHaveURL(/\/login$/);

      await page.goto('/me');
      await expect(page).toHaveURL(/\/login/);
      await second.page.goto('/me');
      await expect(second.page).toHaveURL(/\/login/);
    } finally {
      await second.context.close();
    }
  });

  test('гість на /me/security перенаправляється на /login', async ({ page }) => {
    await page.goto('/me/security');
    await expect(page).toHaveURL(/\/login\?next=%2Fme%2Fsecurity/);
  });
});
