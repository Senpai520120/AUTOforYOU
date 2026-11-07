/**
 * E2E: журнал аудиту і блокування користувачів (задача 1.13).
 * Дані — e2e_seed. Адміністратора (role=admin/суперкористувача) і заблокованого користувача e2e_seed
 * поки не створює, тому сценарії з ними — test.fixme до додавання учёток у e2e_seed.
 * Не-admin співробітник — broker@e2e.test (is_staff, роль broker).
 */
import { test, expect } from './fixtures';

const PASSWORD = process.env.E2E_PASSWORD ?? '';
const AUDIT_URL = '/admin/audit/auditlog/';

async function adminLogin(page: import('@playwright/test').Page, email: string) {
  await page.goto('/admin/login/?next=/admin/');
  await page.getByLabel(/email|користувач|username/i).fill(email);
  await page.getByLabel(/пароль|password/i).fill(PASSWORD);
  await page.getByRole('button', { name: /увійти|log in/i }).click();
  await expect(page).toHaveURL(/\/admin\/$/);
}

test.describe('Журнал аудиту (1.13)', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('обхід: співробітник без ролі admin отримує 403 на журналі', async ({ page }) => {
    await adminLogin(page, 'broker@e2e.test');
    const resp = await page.goto(AUDIT_URL);
    expect(resp?.status()).toBe(403);
    await page.goto('/admin/');
    await expect(page.getByRole('link', { name: 'Журнал аудиту' })).toHaveCount(0);
  });

  test('обхід: гість на журналі — вхід в адмінку', async ({ page }) => {
    await page.goto(AUDIT_URL);
    await expect(page).toHaveURL(/\/admin\/login\//);
  });

  test.fixme('1.13 → e2e_seed: admin блокує з причиною, запис у журналі з автором і причиною; заблокований бачить текст без причини', async ({ page }) => {
    await adminLogin(page, 'admin@e2e.test');
    await page.goto('/admin/users/customuser/?q=seller%40e2e.test');
    await page.locator('input[name="_selected_action"]').first().check();
    await page.locator('select[name="action"]').selectOption('ban_users');
    await page.getByRole('button', { name: /виконати|go/i }).click();
    await page.getByLabel('Вкажіть причину блокування').fill('[E2E] Спам');
    await page.getByRole('button', { name: 'Підтвердити' }).click();
    await page.goto(AUDIT_URL);
    await expect(page.getByRole('row').filter({ hasText: '[E2E] Спам' })).toHaveCount(1);
  });

  test.fixme('1.13 → e2e_seed: блокування без причини показує помилку і нікого не блокує', async ({ page }) => {
    await adminLogin(page, 'admin@e2e.test');
    await page.goto('/admin/users/customuser/?q=seller%40e2e.test');
    await page.locator('input[name="_selected_action"]').first().check();
    await page.locator('select[name="action"]').selectOption('ban_users');
    await page.getByRole('button', { name: /виконати|go/i }).click();
    await page.getByRole('button', { name: 'Підтвердити' }).click();
    await expect(page.getByRole('alert')).toHaveText("Причину блокування вказати обов'язково");
  });

  test.fixme('1.13 → e2e_seed: заблокований на /login бачить «Акаунт заблоковано. Зверніться до підтримки», старий access → 401', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill('blocked@e2e.test');
    await page.getByLabel('Пароль').fill(PASSWORD);
    await page.getByRole('button', { name: 'Увійти' }).click();
    await expect(page.getByRole('alert')).toHaveText('Акаунт заблоковано. Зверніться до підтримки');
  });
});
