/**
 * E2E: права доступу (задача 1.11). Власник бачить своє; гість і сторонній — ні.
 * Дані — e2e_seed: діалог buyer↔seller, оголошення seller. Сторонній — dealer.
 */
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

const ME_PATHS = [
  '/me',
  '/me/messages',
  '/me/deals',
  '/me/local-listings',
  '/me/calculations',
  '/me/shipments',
  '/me/favorites',
  '/me/notifications',
  '/me/saved-searches',
  '/me/security',
  '/me/telegram',
  '/me/trusted-shops',
  '/me/leads',
];

test.describe('Гість на сторінках /me/*', () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });
  for (const path of ME_PATHS) {
    test(`${path} → /login`, async ({ page }) => {
      await page.goto(path);
      await expect(page).toHaveURL(/\/login/);
    });
  }
});

test.describe('Власник бачить своє', () => {
  test.use({ storageState: storageStatePath('buyer') });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  test('buyer: діалог із seller і розрахунки/угоди відкриваються', async ({ page }) => {
    await page.goto('/me/messages');
    await page.getByRole('button', { name: /Користувач/ }).click();
    await expect(page.getByText('[E2E] Здравствуйте!').last()).toBeVisible();
    await page.goto('/me/deals');
    await expect(page.getByRole('heading', { name: 'Мої угоди' })).toBeVisible();
    await page.goto('/me/calculations');
    await expect(page.getByRole('heading', { name: 'Мої розрахунки' })).toBeVisible();
  });
});

test.describe('Сторонній не бачить і не змінює чуже', () => {
  test('dealer відкриває діалог buyer↔seller: помилка, тексту листування немає', async ({ browser, api }) => {
    const convs = await (await api('buyer')).get('/api/v1/messages/conversations/');
    expect(convs.status()).toBe(200);
    const convId = (await convs.json())[0].id;

    const ctx = await browser.newContext({ storageState: storageStatePath('dealer') });
    const page = await ctx.newPage();
    await page.addInitScript(consentInit);
    await page.goto(`/me/messages?conv=${convId}`);
    await expect(page.getByText('Не вдалось завантажити діалог.')).toBeVisible();
    await expect(page.getByText('[E2E] Здравствуйте!')).toHaveCount(0);
    await ctx.close();
  });

  test('API: PATCH чужого активного оголошення — 403, GET saved-search — 405, DELETE — 404', async ({ api }) => {
    const seller = await api('seller');
    const mine = await (await seller.get('/api/v1/local/my-listings/')).json();
    const listings = mine.results ?? mine;
    const listing = listings.find((l: { status: string }) => l.status === 'active') ?? listings[0];
    expect(listing.status).toBe('active');
    const created = await seller.post('/api/v1/saved-searches/', {
      data: { name: 'authz e2e', filters: { make: 'Skoda' } },
    });
    expect(created.status()).toBe(201);
    const searchId = (await created.json()).id;

    const dealer = await api('dealer');
    const patch = await dealer.patch(`/api/v1/local/listings/${listing.id}/`, { data: { description: 'чуже' } });
    expect(patch.status()).toBe(403);
    const after = await (await seller.get(`/api/v1/local/listings/${listing.id}/`)).json();
    expect(after.description).toBe(listing.description);
    const get = await dealer.get(`/api/v1/saved-searches/${searchId}/`);
    expect(get.status()).toBe(405);
    const del = await dealer.delete(`/api/v1/saved-searches/${searchId}/`);
    expect(del.status()).toBe(404);

    expect((await seller.delete(`/api/v1/saved-searches/${searchId}/`)).status()).toBe(204);
  });
});
