/**
 * E2E: мобільний smoke (mobile-chrome та mobile-safari, див. playwright.config.ts).
 * Повна мобільна перевірка (горизонтальний скрол, форми) — 23-P43/P44 у задачі 6.1.
 */
import { test, expect } from './fixtures';

test.describe('Мобільний smoke @mobile', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  for (const [path, heading] of [
    ['/', 'Авто з США під ключ в Україну'],
    ['/listings', 'Каталог автомобілів'],
    ['/ua', 'Каталог Україна'],
    ['/calculator', 'Калькулятор вартості «під ключ»'],
  ] as const) {
    test(`${path} відкривається, h1 видно`, async ({ page }) => {
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(200);
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
    });
  }

  test('розрахунок у калькуляторі проходить', async ({ page }) => {
    await page.goto('/calculator');
    await page.getByLabel('Ціна аукціону ($)', { exact: true }).fill('5000');
    await page.getByLabel("Об'єм двигуна (см³)", { exact: true }).fill('2000');
    await page.getByLabel('Рік випуску', { exact: true }).fill('2018');
    await page.getByRole('button', { name: 'Розрахувати' }).click();

    await expect(page.getByRole('heading', { name: 'Детализация стоимости «под ключ»' })).toBeVisible();
    const total = page.getByRole('row').filter({ hasText: 'ИТОГО' });
    await expect(total).toBeVisible();
    await expect(total).not.toContainText('—');
  });

  test('вхід на мобільному → /me', async ({ page }) => {
    const password = process.env.E2E_PASSWORD;
    if (!password) throw new Error('E2E_PASSWORD не задано.');
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('buyer@e2e.test');
    await page.locator('input[type="password"]').fill(password);
    await page.getByRole('button', { name: 'Увійти' }).click();

    await expect(page).toHaveURL(/\/me$/);
    await expect(page.getByText('buyer@e2e.test').first()).toBeVisible();
  });

  test('невірний пароль на мобільному → повідомлення, лишаємось на /login', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('buyer@e2e.test');
    await page.locator('input[type="password"]').fill('definitely-wrong-password');
    await page.getByRole('button', { name: 'Увійти' }).click();

    await expect(page.getByText('Невірний email або пароль')).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test.fixme('08-Q4 → задача 6.1: навігація шапки на мобільному (бургер-меню)', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /меню/i }).click();
    await page.getByRole('link', { name: 'Калькулятор' }).click();
    await expect(page).toHaveURL(/\/calculator$/);
  });
});
