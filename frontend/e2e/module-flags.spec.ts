/**
 * E2E: заморозка модулей (задача 2.8). Стек поднят с LOTS/B2B/DEALERS/SHIPMENTS/LEGACY_CARS = false (как прод).
 * Запускать из frontend/ на e2e-стеке (docker-compose.e2e.yml).
 */
import { test, expect } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

test.describe('Модули заморожены: интерфейс @smoke', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  test('главная ведет в калькулятор; в шапке нет каталога лотов, B2B и дилеров', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'Порахувати вартість' })).toBeVisible();

    const nav = page.getByRole('banner');
    for (const href of ['/listings', '/b2b', '/dealers/apply']) {
      await expect(nav.locator(`a[href="${href}"]`)).toHaveCount(0);
    }
    await expect(page.locator('main a[href="/listings"]')).toHaveCount(0);
  });

  test('sitemap без /listings, robots закрывает замороженные разделы', async ({ request }) => {
    const sitemap = await (await request.get('/sitemap.xml')).text();
    expect(sitemap).not.toContain('/listings');

    const robots = await (await request.get('/robots.txt')).text();
    expect(robots).not.toMatch(/Allow: \/listings/);
    for (const path of ['/listings', '/b2b', '/dealers']) {
      expect(robots).toContain(`Disallow: ${path}`);
    }
  });

  test('страница 404 ведет на калькулятор', async ({ page }) => {
    const resp = await page.goto('/no-such-page-2-8');
    expect(resp?.status()).toBe(404);
    await expect(page.getByRole('link', { name: 'Порахувати вартість' })).toHaveAttribute('href', '/calculator');
  });
});

test.describe('Модули заморожены: обход по прямой ссылке', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  for (const path of ['/listings', '/listings/1', '/b2b', '/dealers/apply']) {
    test(`${path} → 404`, async ({ page }) => {
      await page.addInitScript(consentInit);
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(404);
      await expect(page.getByRole('heading', { name: 'Сторінку не знайдено' })).toBeVisible();
    });
  }

  // app/me/loading.tsx запускає стрим до layout сегмента shipments, тому статус уже 200:
  // notFound() посеред стриму дає сторінку 404 і noindex (next/dist/docs/01-app/02-guides/streaming.md,
  // «The HTTP contract»). Дані закриває API: /api/v1/auth/me/shipments/ → 404 (тест нижче).
  test('/me/shipments → сторінка 404 з noindex', async ({ page }) => {
    await page.addInitScript(consentInit);
    await page.goto('/me/shipments');
    await expect(page.getByRole('heading', { name: 'Сторінку не знайдено' })).toBeVisible();
    await expect(page.locator('meta[name="robots"][content*="noindex"]').first()).toBeAttached();
  });

  for (const path of [
    '/api/v1/listings/',
    '/api/v1/vehicles/',
    '/api/v1/b2b/board/',
    '/api/v1/shipments/',
    '/api/v1/auth/me/shipments/',
    '/api/calculate/',
    '/api/list/',
  ]) {
    test(`GET ${path} → 404`, async ({ request }) => {
      expect((await request.get(path)).status()).toBe(404);
    });
  }

  test('NHTSA-декодер VIN не заморожен', async ({ request }) => {
    expect((await request.get('/api/v1/vehicles/SHORT/decode/')).status()).toBe(400);
  });
});

test.describe('Модули заморожены: вошедший пользователь', () => {
  test('buyer: POST /api/v1/listings/create/ → 404 (раньше проверки прав)', async ({ api }) => {
    const buyer = await api('buyer');
    expect((await buyer.post('/api/v1/listings/create/', { data: {} })).status()).toBe(404);
  });

  test('staff: даже администратору замороженные API отвечают 404', async ({ api }) => {
    const staff = await api('staff');
    expect((await staff.get('/api/v1/listings/')).status()).toBe(404);
    expect((await staff.get('/api/v1/vehicles/')).status()).toBe(404);
  });

  test('/me без плитки контейнеров', async ({ browser, asRole }) => {
    const ctx = await browser.newContext({ storageState: asRole('buyer') });
    const page = await ctx.newPage();
    await page.addInitScript(consentInit);
    await page.goto('/me');
    await expect(page.getByRole('link', { name: /Мої розрахунки/ })).toBeVisible();
    await expect(page.locator('a[href="/me/shipments"]')).toHaveCount(0);
    await ctx.close();
  });

  test('site-settings отдает флаги выключенными', async ({ request }) => {
    const data = await (await request.get('/api/v1/site-settings/')).json();
    expect(data).toMatchObject({
      lots_enabled: false, b2b_enabled: false, dealers_enabled: false, shipments_enabled: false,
    });
  });
});
