import { test, expect, storageStatePath } from './fixtures';

test.describe('Авторизація — smoke', () => {
  test.describe('buyer зі storageState', () => {
    test.use({ storageState: storageStatePath('buyer') });

    test('бачить свій email на /me', async ({ page }) => {
      await page.goto('/me');
      await expect(page).toHaveURL(/\/me/);
      await expect(page.getByText('buyer@e2e.test').first()).toBeVisible();
    });
  });

  test.describe('гість', () => {
    test.use({ storageState: { cookies: [], origins: [] } });

    test('на /me перенаправляється на /login', async ({ page }) => {
      await page.goto('/me');
      await expect(page).toHaveURL(/\/login/);
    });
  });
});

test.describe('Мобільна заглушка @mobile', () => {
  test('головна відкривається', async ({ page }) => {
    const resp = await page.goto('/');
    expect(resp?.ok()).toBeTruthy();
    await expect(page.locator('body')).toBeVisible();
  });
});
