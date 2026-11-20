/**
 * E2E: советы «Як перевірити авто» на карточке C2C и отсутствие ссылок на закрытые флагами разделы (задача 10.29).
 * Режим читается из /api/v1/site-settings/; блоки чужих режимов пропускаются через test.skip с причиной
 * (как в c2c-flag.spec.ts). Тексты советов - `[E2E]` из e2e_seed.
 */
import { test, expect } from './fixtures';

const GUEST = { cookies: [], origins: [] };
let c2cOn = false;
let listingId: number | null = null;
let tips = '';

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  const res = await ctx.get('/api/v1/site-settings/');
  expect(res.status()).toBe(200);
  const body = await res.json();
  c2cOn = body.c2c_enabled === true;
  tips = String(body.listing_check_tips ?? '');
  if (c2cOn) {
    const list = await ctx.get('/api/v1/local/listings/');
    listingId = (await list.json()).results?.[0]?.id ?? null;
  }
  await ctx.dispose();
});

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('C2C выключен: нет ссылок на закрытое', () => {
  test.beforeEach(() => test.skip(c2cOn, 'стек с C2C_ENABLED=true'));
  test.use({ storageState: GUEST });

  test('шапка, подвал и главная без /ua и /local/new @smoke', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('banner')).toBeVisible();
    for (const href of ['/ua', '/local/new']) {
      await expect(page.locator(`header a[href="${href}"]`)).toHaveCount(0);
      await expect(page.locator(`footer a[href="${href}"]`)).toHaveCount(0);
      await expect(page.locator(`main a[href="${href}"]`)).toHaveCount(0);
    }
  });

  test('sitemap без /ua и /local/', async ({ request }) => {
    const sitemap = await (await request.get('/sitemap.xml')).text();
    expect(sitemap).not.toContain('/ua');
    expect(sitemap).not.toContain('/local/');
  });
});

test.describe('C2C включён: советы на карточке', () => {
  test.beforeEach(() => {
    test.skip(!c2cOn, 'стек с C2C_ENABLED=false');
    test.skip(listingId === null, 'в каталоге нет объявлений (запустите e2e_seed)');
  });
  test.use({ storageState: GUEST });

  test('блок советов показан, тексты из настроек', async ({ page }) => {
    test.skip(!tips.includes('[E2E]'), 'listing_check_tips не заполнен (стек без e2e_seed)');
    await page.goto(`/local/${listingId}`);
    const block = page.getByTestId('listing-check-tips');
    await expect(block).toBeVisible();
    await expect(block.getByRole('heading', { name: 'Як перевірити авто перед купівлею' })).toBeVisible();
    await expect(block.getByRole('listitem')).toHaveCount(tips.split('\n').filter((l) => l.trim()).length);
  });

  test('при пустых настройках блока нет', async ({ page }) => {
    test.skip(tips.trim() !== '', 'советы заполнены');
    await page.goto(`/local/${listingId}`);
    await expect(page.getByTestId('listing-check-tips')).toHaveCount(0);
  });
});
