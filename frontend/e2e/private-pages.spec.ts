/**
 * E2E: закриті сторінки (23-P2).
 * Захист клієнтський (useRequireAuth, задача 1.4): гість → /login?next=<шлях>.
 */
import { test, expect, storageStatePath } from './fixtures';

const PRIVATE_PATHS = [
  '/me',
  '/me/favorites',
  '/me/local-listings',
  '/me/messages',
  '/b2b',
  '/local/new',
  '/dealers/apply',
];

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

test.describe('Гість на закритих сторінках', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  for (const path of PRIVATE_PATHS) {
    test(`${path} → /login`, async ({ page }) => {
      await page.goto(path);
      await expect(page).toHaveURL(/\/login/);
      await expect(page.getByRole('heading', { name: 'Вхід' })).toBeVisible();
    });
  }

  test('08-S7: після входу повертає на сторінку з ?next=', async ({ page }) => {
    await page.goto('/me/favorites');
    await expect(page).toHaveURL(/\/login\?next=%2Fme%2Ffavorites/);
    await page.waitForLoadState('networkidle'); // форма має гідратуватися до кліку
    await page.locator('input[type="email"]').fill('buyer@e2e.test');
    await page.locator('input[type="password"]').fill(process.env.E2E_PASSWORD ?? '');
    await page.getByRole('button', { name: 'Увійти' }).click();
    await expect(page).toHaveURL(/\/me\/favorites$/);
  });

  test('10-S7: зовнішній next ігнорується', async ({ page, baseURL }) => {
    await page.goto('/login?next=https://evil.example/');
    await page.waitForLoadState('networkidle');
    await page.locator('input[type="email"]').fill('buyer@e2e.test');
    await page.locator('input[type="password"]').fill(process.env.E2E_PASSWORD ?? '');
    await page.getByRole('button', { name: 'Увійти' }).click();
    await expect(page).toHaveURL(/\/me$/);
    expect(new URL(page.url()).origin).toBe(new URL(baseURL!).origin);
  });

  test.fixme('08-S7 → задача 6.2: серверний редірект без JS (proxy.ts за cookie has_session)', async ({ request }) => {
    const resp = await request.get('/me', { maxRedirects: 0 });
    expect([307, 308]).toContain(resp.status());
    expect(resp.headers()['location']).toMatch(/\/login/);
  });
});

test.describe('buyer на закритих сторінках', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  for (const path of PRIVATE_PATHS) {
    test(`${path} відкривається без редіректу`, async ({ page }) => {
      await page.goto(path);
      // Редірект на /login відбувається в useEffect після завантаження профілю, тож спершу
      // дочікуємось авторизованого стану шапки, інакше перевірка URL хибно-зелена.
      await expect(page.getByRole('banner').getByRole('button', { name: 'Вийти' })).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`${path}$`));
    });
  }
});
