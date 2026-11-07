/**
 * E2E: задача 1.17 (D1, D2) — регістр email і відкликання сесій при зміні пароля поза API.
 *
 * (в) У e2e-сідері немає суперкористувача для форми «Змінити пароль» в адмінці, тому пароль міняється
 * тим самим кодом, що й форма/`changepassword` (set_password + save → CustomUser відкликає сесії),
 * через `manage.py shell` у контейнері backend e2e-стека. Контейнер шукається за label compose-проєкту
 * (E2E_COMPOSE_PROJECT, за замовчуванням autoforyou-e2e); без docker тест пропускається.
 */
import { execFileSync } from 'child_process';
import type { Browser, Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { registerViaApi } from './helpers/captcha';

test.use({ storageState: { cookies: [], origins: [] } });

const ADMIN_SET_PASSWORD = 'Admin-Zmina-6154!';

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

function mixedCase(email: string): string {
  const [local, domain] = email.split('@');
  return `${local.toUpperCase()}@${domain.toUpperCase()}`;
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

/** Імітація «адмін змінив пароль»: той самий код, що в формі адмінки і `changepassword`. */
function adminChangesPassword(email: string, password: string) {
  const project = process.env.E2E_COMPOSE_PROJECT ?? 'autoforyou-e2e';
  let container = '';
  try {
    container = execFileSync('docker', [
      'ps', '-q',
      '--filter', `label=com.docker.compose.project=${project}`,
      '--filter', 'label=com.docker.compose.service=backend',
    ]).toString().trim().split('\n')[0];
  } catch {
    return false;
  }
  if (!container) return false;
  execFileSync('docker', [
    'exec', '-e', `E2E_TARGET=${email}`, '-e', `E2E_NEW_PW=${password}`, container,
    'python', 'manage.py', 'shell', '-c',
    "import os; from django.contrib.auth import get_user_model; "
    + "u = get_user_model().objects.get_by_natural_key(os.environ['E2E_TARGET']); "
    + "u.set_password(os.environ['E2E_NEW_PW']); u.save()",
  ]);
  return true;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Регістр email (1.17, D2)', () => {
  test('реєстрація, вхід з тим самим email в іншому регістрі — успіх', async ({ page, uniqueEmail }) => {
    const password = e2ePassword();
    await page.goto('/register');
    await page.locator('input[type="email"]').fill(uniqueEmail);
    await page.locator('input[type="password"]').first().fill(password);
    await page.locator('input[type="password"]').nth(1).fill(password);
    await page.getByLabel(/Погоджуюсь з/).check();
    await page.getByLabel(/18 років/).check();
    await page.getByRole('button', { name: 'Зареєструватися' }).click();
    await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();

    await uiLogin(page, mixedCase(uniqueEmail), password);
    await expect(page).toHaveURL(/\/me$/);
    await expect(page.getByText(uniqueEmail).first()).toBeVisible();
  });

  test('повторна реєстрація в іншому регістрі — нейтральний екран, не «акаунт створено»', async ({
    page, request, uniqueEmail,
  }) => {
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);

    await page.goto('/register');
    await page.locator('input[type="email"]').fill(mixedCase(uniqueEmail));
    await page.locator('input[type="password"]').first().fill(password);
    await page.locator('input[type="password"]').nth(1).fill(password);
    await page.getByLabel(/Погоджуюсь з/).check();
    await page.getByLabel(/18 років/).check();
    const registerResponse = page.waitForResponse(
      (r) => r.url().includes('/auth/register/') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Зареєструватися' }).click();
    expect((await registerResponse).status()).toBe(201);
    // Той самий екран, що й для нового адреса (01-S11): існування акаунта не розкривається.
    await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();
    await expect(page.getByText(/акаунт (уже )?існує|вже зареєстрован/i)).toHaveCount(0);
  });
});

test.describe('Адмін змінив пароль (1.17, D1)', () => {
  test('сесія другого контексту недійсна після перезавантаження', async ({ browser, request, uniqueEmail }) => {
    test.setTimeout(120_000);
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);

    const second = await newContextPage(browser);
    try {
      await uiLogin(second.page, uniqueEmail, password);
      await expect(second.page).toHaveURL(/\/me$/);

      const changed = adminChangesPassword(uniqueEmail, ADMIN_SET_PASSWORD);
      test.skip(!changed, 'docker/контейнер backend e2e-стека недоступні — змінити пароль нема чим');

      await second.page.reload();
      await second.page.goto('/me');
      await expect(second.page).toHaveURL(/\/login/);

      // Новий пароль працює, старий — ні.
      await uiLogin(second.page, uniqueEmail, ADMIN_SET_PASSWORD);
      await expect(second.page).toHaveURL(/\/me$/);
    } finally {
      await second.context.close();
    }
  });
});
