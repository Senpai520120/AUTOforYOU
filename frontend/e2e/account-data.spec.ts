/**
 * E2E: профіль, вивантаження «Мої дані», видалення акаунта з періодом скасування (задача 1.8, 23-P13).
 *
 * Окремий новий користувач на кожен тест (реєстрація через API, honeypot-капча e2e-стека).
 * Остаточне знеособлення після періоду скасування перевіряє Django-тест задачі
 * anonymize_due_accounts, не Playwright.
 */
import fs from 'fs';
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';
import { registerViaApi } from './helpers/captcha';

test.use({ storageState: { cookies: [], origins: [] } });

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

async function uiLogin(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole('button', { name: 'Увійти' }).click();
  await expect(page).toHaveURL(/\/me$/);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Профіль /me/profile', () => {
  test('успіх: ім’я, прізвище й телефон зберігаються після перезавантаження', async ({ page, request, uniqueEmail }) => {
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    await uiLogin(page, uniqueEmail, password);
    await page.getByRole('link', { name: /Профіль/ }).click();
    await expect(page).toHaveURL(/\/me\/profile$/);

    await page.getByLabel('Ім\'я').fill('Олена');
    await page.getByLabel('Прізвище').fill('Коваль');
    await page.getByLabel('Телефон').fill('+380501234567');
    await page.getByRole('button', { name: 'Зберегти' }).click();
    await expect(page.getByText('Зміни збережено')).toBeVisible();

    await page.reload();
    await expect(page.getByLabel('Ім\'я')).toHaveValue('Олена');
    await expect(page.getByLabel('Прізвище')).toHaveValue('Коваль');
    await expect(page.getByLabel('Телефон')).toHaveValue('+380501234567');
  });

  test('помилка: телефон не у форматі +380 — помилка поля, запиту немає', async ({ page, request, uniqueEmail }) => {
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    await uiLogin(page, uniqueEmail, password);
    await page.goto('/me/profile');
    await page.getByLabel('Телефон').fill('abc');
    await expectNoRequest(
      page,
      (r) => r.method() === 'PATCH' && r.url().includes('/api/v1/auth/profile/'),
      () => page.getByRole('button', { name: 'Зберегти' }).click(),
    );
    await expect(page.getByText('Телефон у форматі +380XXXXXXXXX.')).toBeVisible();
    await expect(page.getByLabel('Телефон')).toHaveAttribute('aria-invalid', 'true');
  });
});

test.describe('Мої дані /me/data', () => {
  test('успіх: «Завантажити мої дані» віддає JSON зі своїм email', async ({ page, request, uniqueEmail }) => {
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    await uiLogin(page, uniqueEmail, password);
    await page.getByRole('link', { name: /Мої дані/ }).click();
    await expect(page).toHaveURL(/\/me\/data$/);

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Завантажити мої дані' }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^autoforyou-data-\d{4}-\d{2}-\d{2}\.json$/);
    const file = await download.path();
    const data = JSON.parse(fs.readFileSync(file!, 'utf-8')) as { profile: { email: string }; consents: unknown[] };
    expect(data.profile.email).toBe(uniqueEmail);
    expect(data.consents.length).toBeGreaterThan(0);
  });

  test('успіх: видалення з паролем → вихід, банер при повторному вході, скасування працює', async ({
    page, request, uniqueEmail,
  }) => {
    test.setTimeout(90_000);
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    await uiLogin(page, uniqueEmail, password);
    await page.goto('/me/data');

    await page.getByLabel('Пароль').fill(password);
    await page.getByLabel('Я розумію, що це незворотно').check();
    await page.getByRole('button', { name: 'Видалити акаунт' }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId('flash-message')).toContainText('Видалення акаунта заплановано');
    // Сесію відкликано: кабінет вимагає входу.
    await page.goto('/me');
    await expect(page).toHaveURL(/\/login/);

    await uiLogin(page, uniqueEmail, password);
    await expect(page.getByTestId('deletion-banner')).toContainText('Акаунт буде видалено');
    await page.getByTestId('deletion-banner').getByRole('link', { name: 'Скасувати видалення' }).click();
    await expect(page).toHaveURL(/\/me\/data$/);
    await page.getByRole('button', { name: 'Скасувати видалення' }).click();
    await expect(page.getByTestId('deletion-scheduled')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Видалити акаунт' })).toBeVisible();

    await page.goto('/me');
    await expect(page.getByRole('link', { name: /Мої дані/ })).toBeVisible();
    await expect(page.getByTestId('deletion-banner')).toHaveCount(0);
  });

  test('обхід: без пароля й підтвердження кнопка неактивна; невірний пароль — текст помилки, акаунт живий', async ({
    page, request, uniqueEmail,
  }) => {
    const password = e2ePassword();
    await registerViaApi(request, uniqueEmail, password);
    await uiLogin(page, uniqueEmail, password);
    await page.goto('/me/data');

    const button = page.getByRole('button', { name: 'Видалити акаунт' });
    await expect(button).toBeDisabled();
    await page.getByLabel('Пароль').fill('wrong-password-123');
    await expect(button).toBeDisabled(); // без «Я розумію…»
    await page.getByLabel('Я розумію, що це незворотно').check();
    await expect(button).toBeEnabled();
    await button.click();
    await expect(page.getByTestId('delete-error')).toHaveText('Невірний пароль.');

    // Акаунт не поставлено на видалення й сесія жива.
    await page.goto('/me');
    await expect(page).toHaveURL(/\/me$/);
    await expect(page.getByTestId('deletion-banner')).toHaveCount(0);
  });
});
