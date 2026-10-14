/**
 * E2E: вхід і вихід (23-P1, 23-P3).
 * Пароль — тільки з E2E_PASSWORD (той самий, з яким виконано e2e_seed).
 */
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';

const GUEST = { cookies: [], origins: [] };

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

test.describe('Вхід (23-P1)', () => {
  test.use({ storageState: GUEST });

  test.beforeEach(async ({ page }) => {
    // Банер згоди — fixed bottom, може перекривати елементи; тут він не предмет перевірки.
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('вірний пароль → /me, у шапці «Вийти» і email', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('seller@e2e.test');
    await page.locator('input[type="password"]').fill(e2ePassword());
    await page.getByRole('button', { name: 'Увійти' }).click();

    await expect(page).toHaveURL(/\/me$/);
    await expect(page.getByRole('banner').getByRole('button', { name: 'Вийти' })).toBeVisible();
    await expect(page.getByText('seller@e2e.test').first()).toBeVisible();
    // Сесія — тільки httpOnly-cookie (задача 1.4).
    expect(await page.evaluate(() => localStorage.getItem('access'))).toBeNull();
    expect(await cookieNames(page)).toContain('access');
  });

  test('невірний пароль → повідомлення, лишаємось на /login, токена немає', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('seller@e2e.test');
    await page.locator('input[type="password"]').fill(`${e2ePassword()}-wrong`);

    const tokenResponse = page.waitForResponse(
      (r) => r.url().includes('/auth/token/') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Увійти' }).click();
    expect((await tokenResponse).status()).toBe(401);

    await expect(page.getByText('Невірний email або пароль')).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
    expect(await cookieNames(page)).not.toContain('access');
    expect(await cookieNames(page)).not.toContain('refresh');
  });
});

test.describe('Вихід (23-P3)', () => {
  // Власний вхід, а не storageState seller: вихід відкликає refresh на сервері,
  // і спільний стан інших тестів зламався б.
  test.use({ storageState: GUEST });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
    const login = await page.request.post('/api/v1/auth/token/', {
      data: { email: 'seller@e2e.test', password: e2ePassword() },
    });
    expect(login.status()).toBe(200);
  });

  test('після «Вийти» /me веде на /login, cookie сесії видалено', async ({ page }) => {
    await page.goto('/me');
    await expect(page.getByText('seller@e2e.test').first()).toBeVisible();

    await page.getByRole('banner').getByRole('button', { name: 'Вийти' }).click();
    await expect(page.getByRole('banner').getByRole('link', { name: 'Увійти' })).toBeVisible();

    expect(await cookieNames(page)).not.toContain('access');
    expect(await cookieNames(page)).not.toContain('refresh');

    await page.goto('/me');
    await expect(page).toHaveURL(/\/login/);
  });
  // Відкликання refresh після виходу (08-S2) — e2e/auth-cookie.spec.ts, 23-P3.
});

async function cookieNames(page: Page): Promise<string[]> {
  return (await page.context().cookies()).map((c) => c.name);
}
