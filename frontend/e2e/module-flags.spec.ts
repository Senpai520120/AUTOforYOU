/**
 * E2E: замороженные модули (задача 2.8). Выполняется только на стеке с LOTS/B2B/DEALERS/SHIPMENTS_ENABLED=false
 * (как на проде). Обычный e2e-стек держит флаги true ради спеков самих модулей — тогда спек пропускается
 * с пометкой; запуск: стек с флагами false, затем `npx playwright test e2e/module-flags.spec.ts`.
 */
import { test, expect, storageStatePath } from './fixtures';

test.use({ storageState: storageStatePath('buyer') });

test.beforeEach(async ({ page }) => {
  const flags = await (await page.request.get('/api/v1/site-settings/')).json();
  const anyOn = flags.lots_enabled || flags.b2b_enabled || flags.dealers_enabled || flags.shipments_enabled;
  test.skip(anyOn, 'стек з увімкненими модулями — 2.8 перевіряється на стеку з прапорами false');
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Заморожені модулі: навігація без них', () => {
  test('головна: «Порахувати вартість», без «Пригін/аукціон», B2B і «B2B-доступ»', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'Порахувати вартість' }).first()).toBeVisible();
    const header = page.locator('header');
    await expect(header.getByRole('link', { name: 'Пригін/аукціон' })).toHaveCount(0);
    await expect(header.getByRole('link', { name: 'B2B', exact: true })).toHaveCount(0);
    await expect(header.getByRole('link', { name: 'B2B-доступ' })).toHaveCount(0);
    await expect(page.locator('a[href="/listings"], a[href="/b2b"], a[href="/dealers/apply"]')).toHaveCount(0);
  });

  test('кабінет без плитки «Мої контейнери»', async ({ page }) => {
    await page.goto('/me');
    await expect(page.locator('a[href="/me/calculations"]')).toBeVisible();
    await expect(page.locator('a[href="/me/shipments"]')).toHaveCount(0);
  });

  test('sitemap і robots без каталогу лотів', async ({ page }) => {
    const sitemap = await (await page.request.get('/sitemap.xml')).text();
    expect(sitemap).toContain('/calculator');
    expect(sitemap).not.toContain('/listings');
    const robots = await (await page.request.get('/robots.txt')).text();
    expect(robots).not.toMatch(/Allow: \/listings/);
    expect(robots).toMatch(/Disallow: \/listings/);
  });

  test('сторінка 404 веде на калькулятор', async ({ page }) => {
    await page.goto('/this-page-does-not-exist-xyz');
    await expect(page.getByRole('link', { name: 'Розрахувати вартість' })).toHaveAttribute('href', '/calculator');
  });
});

test.describe('Заморожені модулі: прямий захід і API — 404', () => {
  for (const path of ['/listings', '/listings/1', '/b2b', '/dealers/apply', '/me/shipments']) {
    test(`сторінка ${path} → 404`, async ({ page }) => {
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(404);
    });
  }

  for (const path of ['/api/v1/listings/', '/api/v1/vehicles/', '/api/v1/b2b/board/', '/api/v1/shipments/',
    '/api/v1/auth/me/shipments/', '/api/calculate/', '/api/list/']) {
    test(`API ${path} → 404`, async ({ page }) => {
      expect((await page.request.get(path)).status()).toBe(404);
    });
  }

  test('POST /api/v1/listings/create/ від buyer → 404 (не 403: модуль вимкнено раніше перевірки прав)', async ({ page }) => {
    await page.goto('/');
    const csrf = (await page.context().cookies()).find(c => c.name === 'csrftoken')?.value ?? '';
    const resp = await page.request.post('/api/v1/listings/create/', { data: {}, headers: { 'X-CSRFToken': csrf } });
    expect(resp.status()).toBe(404);
  });
});
