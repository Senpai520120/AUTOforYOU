/**
 * E2E: реєстрація до кінця (23-P6).
 * Задача 1.6: чекбокс «Мені виповнилося 18 років», капча (у e2e-стеку honeypot), замість
 * /login?registered=1 — екран «Перевірте пошту».
 */
import { test, expect } from './fixtures';

test.use({ storageState: { cookies: [], origins: [] } });

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

test.describe('Реєстрація до кінця (23-P6)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('реєстрація → «Перевірте пошту» → вхід → /me з цим email', async ({ page, uniqueEmail }) => {
    const password = e2ePassword();
    await page.goto('/register');
    await page.locator('input[type="email"]').fill(uniqueEmail);
    await page.locator('input[type="password"]').first().fill(password);
    await page.locator('input[type="password"]').nth(1).fill(password);
    await page.getByLabel(/Погоджуюсь з/).check();
    await page.getByLabel(/18 років/).check();
    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();
    await page.getByRole('link', { name: 'Перейти до входу' }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.locator('input[type="email"]').fill(uniqueEmail);
    await page.locator('input[type="password"]').fill(password);
    await page.getByRole('button', { name: 'Увійти' }).click();

    await expect(page).toHaveURL(/\/me$/);
    await expect(page.getByText(uniqueEmail).first()).toBeVisible();
  });

  test('дубль email → той самий екран «Перевірте пошту», без розкриття (01-S11)', async ({ page }) => {
    const password = e2ePassword();
    await page.goto('/register');
    await page.locator('input[type="email"]').fill('buyer@e2e.test');
    await page.locator('input[type="password"]').first().fill(password);
    await page.locator('input[type="password"]').nth(1).fill(password);
    await page.getByLabel(/Погоджуюсь з/).check();
    await page.getByLabel(/18 років/).check();

    const registerResponse = page.waitForResponse(
      (r) => r.url().includes('/auth/register/') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Зареєструватися' }).click();
    expect((await registerResponse).status()).toBe(201);
    await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();
  });
});
