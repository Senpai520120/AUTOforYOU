import { test, expect, storageStatePath } from './fixtures';

test.describe('Ролі і права (1.2)', () => {
  test.describe('верифікований дилер', () => {
    test.use({ storageState: storageStatePath('dealer') });
    test('бачить дошку B2B, а не «Доступ обмежено»', async ({ page }) => {
      await page.goto('/b2b');
      await expect(page.getByRole('heading', { name: 'Доступ обмежено' })).toHaveCount(0);
      await expect(page).toHaveURL(/\/b2b/);
    });
  });

  test.describe('самозваний admin', () => {
    test.use({ storageState: storageStatePath('fakeadmin') });
    test('роль admin без is_staff і верифікації: на /b2b «Доступ обмежено» (09-S2)', async ({ page }) => {
      await page.goto('/b2b');
      await expect(page.getByRole('heading', { name: 'Доступ обмежено' })).toBeVisible();
    });
  });

  test.describe('брокер', () => {
    test.use({ storageState: storageStatePath('broker') });
    test('у /me мітка «Брокер»', async ({ page }) => {
      await page.goto('/me');
      await expect(page.getByText('Брокер', { exact: true })).toBeVisible();
    });
    test('is_staff не дає B2B: у шапці немає посилання «B2B», на /b2b «Доступ обмежено» (1.2b)', async ({ page }) => {
      await page.goto('/b2b');
      await expect(page.getByRole('heading', { name: 'Доступ обмежено' })).toBeVisible();
      await expect(page.getByRole('link', { name: 'B2B', exact: true })).toHaveCount(0);
    });
  });

  test('на формі реєстрації немає вибору ролі', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByLabel(/Погоджуюсь з/)).toBeVisible();
    await expect(page.locator('select')).toHaveCount(0);
    await expect(page.getByText('Перекупник')).toHaveCount(0);
  });
});
