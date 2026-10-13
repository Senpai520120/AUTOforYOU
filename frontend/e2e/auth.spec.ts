/**
 * E2E: вхід і вихід (23-P1, 23-P3).
 * Пароль — тільки з E2E_PASSWORD (той самий, з яким виконано e2e_seed).
 */
import fs from 'fs';
import { test, expect, storageStatePath } from './fixtures';

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
    expect(await page.evaluate(() => localStorage.getItem('access'))).toBeTruthy();
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
    expect(await page.evaluate(() => localStorage.getItem('access'))).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem('refresh'))).toBeNull();
  });
});

test.describe('Вихід (23-P3)', () => {
  test.use({ storageState: storageStatePath('seller') });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('після «Вийти» /me веде на /login, токенів у localStorage немає', async ({ page }) => {
    await page.goto('/me');
    await expect(page.getByText('seller@e2e.test').first()).toBeVisible();

    await page.getByRole('banner').getByRole('button', { name: 'Вийти' }).click();
    await expect(page.getByRole('banner').getByRole('link', { name: 'Увійти' })).toBeVisible();

    expect(await page.evaluate(() => localStorage.getItem('access'))).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem('refresh'))).toBeNull();

    await page.goto('/me');
    await expect(page).toHaveURL(/\/login/);
  });

  test.fixme('08-S2 → задача 1.4: refresh після виходу відхилено сервером', async ({ page, request }) => {
    const state = JSON.parse(fs.readFileSync(storageStatePath('seller'), 'utf-8'));
    const refresh = state.origins
      .flatMap((o: { localStorage: { name: string; value: string }[] }) => o.localStorage)
      .find((i: { name: string }) => i.name === 'refresh')?.value;
    expect(refresh).toBeTruthy();

    await page.goto('/me');
    await page.getByRole('banner').getByRole('button', { name: 'Вийти' }).click();
    await expect(page.getByRole('banner').getByRole('link', { name: 'Увійти' })).toBeVisible();

    const resp = await request.post('/api/v1/auth/token/refresh/', { data: { refresh } });
    expect(resp.status()).toBe(401);
  });
});
