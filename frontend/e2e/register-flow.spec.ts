/**
 * E2E: реєстрація до кінця (23-P6).
 * Після задачі 1.6 сценарій змінюється: чекбокс «Мені виповнилося 18 років», капча на
 * тестовому ключі Turnstile, замість /login?registered=1 — екран «Перевірте пошту».
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

  test('реєстрація → /login?registered=1 → вхід → /me з цим email', async ({ page, uniqueEmail }) => {
    const password = e2ePassword();
    await page.goto('/register');
    await page.locator('input[type="email"]').fill(uniqueEmail);
    await page.locator('input[type="password"]').first().fill(password);
    await page.locator('input[type="password"]').nth(1).fill(password);
    await page.getByLabel(/Погоджуюсь з/).check();
    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    await expect(page).toHaveURL(/\/login\?registered=1/);

    await page.locator('input[type="email"]').fill(uniqueEmail);
    await page.locator('input[type="password"]').fill(password);
    await page.getByRole('button', { name: 'Увійти' }).click();

    await expect(page).toHaveURL(/\/me$/);
    await expect(page.getByText(uniqueEmail).first()).toBeVisible();
  });

  test('дубль email → помилка сервера показується на сторінці', async ({ page }) => {
    const password = e2ePassword();
    await page.goto('/register');
    await page.locator('input[type="email"]').fill('buyer@e2e.test');
    await page.locator('input[type="password"]').first().fill(password);
    await page.locator('input[type="password"]').nth(1).fill(password);
    await page.getByLabel(/Погоджуюсь з/).check();

    const registerResponse = page.waitForResponse(
      (r) => r.url().includes('/auth/register/') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Зареєструватися' }).click();
    const resp = await registerResponse;
    expect(resp.status()).toBe(400);

    // Очікуваний текст беремо з відповіді сервера (сторінка склеює повідомлення через ". "),
    // а не з класу елемента (13-Q4).
    const body = (await resp.json()) as Record<string, string[]>;
    const expected = Object.values(body).flat().join('. ');
    expect(expected.length).toBeGreaterThan(0);

    await expect(page.getByText(expected, { exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/register/);
  });
});
