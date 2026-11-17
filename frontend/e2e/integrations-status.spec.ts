import { test, expect, storageStatePath } from './fixtures';

// Сторінка статусу інтеграцій у Django Admin (задача 3.1, 23-P27).
test.describe('Статус інтеграцій в адмінці (3.1)', () => {
  // Потрібен суперкористувач адмінки з правом integrations.view_integrationhealth, а e2e_seed його не створює
  // (staff@e2e.test - лише is_staff без прав). Знімати fixme після додавання такого користувача в e2e_seed.
  test.fixme('3.1 → e2e_seed: суперкористувач бачить таблицю ≥ 8 рядків, Opendatabot «Не налаштовано», значення ключа немає', async ({ page }) => {
    await page.goto('/admin/login/?next=/admin/');
    await page.getByLabel(/email|користувач|username/i).fill(`admin@e2e.test`);
    await page.getByLabel(/пароль|password/i).fill(process.env.E2E_PASSWORD ?? '');
    await page.getByRole('button', { name: /увійти|log in/i }).click();
    await page.getByRole('link', { name: 'Статус інтеграцій' }).click();
    await expect(page.locator('#integrations-status-table tbody tr')).toHaveCount(8);
    const row = page.locator('tr[data-provider="opendatabot"]');
    await expect(row).toContainText('Не налаштовано');
    await expect(row).toContainText('OPENDATABOT_API_KEY');
  });

  test.describe('звичайний користувач', () => {
    test.use({ storageState: storageStatePath('buyer') });
    test('обхід: /admin/integrations/status/ веде на вхід в адмінку, таблиці немає', async ({ page }) => {
      await page.goto('/admin/integrations/status/');
      await expect(page).toHaveURL(/\/admin\/login\//);
      await expect(page.locator('#integrations-status-table')).toHaveCount(0);
    });
  });
});
