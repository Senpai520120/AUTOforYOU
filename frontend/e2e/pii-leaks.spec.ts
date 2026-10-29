/**
 * E2E: ПДн не утікають через API-серіалізатори та SSR (задача 1.9).
 * Власник без імені бачить керування карткою через is_owner; email/телефон/локальна частина
 * email продавця не потрапляють у SSR-HTML, модалку «продано» і /me/deals.
 */
import type { APIRequestContext } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const SELLER_EMAIL = 'seller@e2e.test';
const BUYER_EMAIL = 'buyer@e2e.test';
const PHONE = '+380677001122';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(consentInit);
});

async function activeListingId(api: APIRequestContext) {
  const resp = await api.get('/api/v1/local/my-listings/');
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  const rows = Array.isArray(body) ? body : body.results;
  const row = rows.find((l: { status: string; description: string }) =>
    l.status === 'active' && l.description.startsWith('[E2E]'));
  expect(row).toBeTruthy();
  return row.id as number;
}

test.describe('Власник і покупець C2C-оголошення', () => {
  test('власник без імені бачить «Редагувати»; покупець бачить телефон; SSR без ПДн', async ({ browser, api, request }) => {
    const sellerApi = await api('seller');
    const id = await activeListingId(sellerApi);
    const patched = await sellerApi.patch(`/api/v1/local/listings/${id}/`, { data: { contact_phone: PHONE } });
    expect(patched.status()).toBe(200);

    // Власник (без імені й прізвища): кнопка керування приходить через is_owner.
    const ownerCtx = await browser.newContext({ storageState: storageStatePath('seller') });
    const ownerPage = await ownerCtx.newPage();
    await ownerPage.addInitScript(consentInit);
    await ownerPage.goto(`/local/${id}`);
    await expect(ownerPage.getByRole('link', { name: 'Редагувати' })).toBeVisible();
    await ownerCtx.close();

    // Покупець: керування немає, телефон з'являється за кнопкою.
    const buyerCtx = await browser.newContext({ storageState: storageStatePath('buyer') });
    const buyerPage = await buyerCtx.newPage();
    await buyerPage.addInitScript(consentInit);
    await buyerPage.goto(`/local/${id}`);
    await expect(buyerPage.getByRole('link', { name: 'Редагувати' })).toHaveCount(0);
    await buyerPage.getByRole('button', { name: 'Показати телефон' }).click();
    await expect(buyerPage.getByRole('link', { name: PHONE })).toBeVisible();
    await buyerCtx.close();

    // SSR-HTML (гість): ні телефону, ні email, ні локальної частини email.
    const html = await (await request.get(`/local/${id}`)).text();
    expect(html).not.toContain(PHONE);
    expect(html).not.toContain('380677001122');
    expect(html).not.toContain(SELLER_EMAIL);
    expect(html).not.toContain('seller@');
    expect(html).toContain('Користувач');
  });

  test('модалка «продано» і /me/deals не показують email співрозмовника', async ({ browser, api }) => {
    const sellerApi = await api('seller');
    const id = await activeListingId(sellerApi);

    const sellerCtx = await browser.newContext({ storageState: storageStatePath('seller') });
    const sellerPage = await sellerCtx.newPage();
    await sellerPage.addInitScript(consentInit);
    await sellerPage.goto('/me/local-listings');
    const row = sellerPage.locator('div.rounded-xl', { has: sellerPage.locator(`a[href="/local/${id}"]`) }).last();
    await row.getByRole('button', { name: /Позначити проданим/ }).click();
    const modal = sellerPage.getByRole('heading', { name: 'Позначити як продано' }).locator('xpath=ancestor::div[1]');
    await expect(modal.getByRole('button', { name: 'Користувач' }).first()).toBeVisible();
    await expect(sellerPage.locator('body')).not.toContainText(BUYER_EMAIL);
    await expect(sellerPage.locator('body')).not.toContainText('buyer@');
    await sellerCtx.close();

    // Угода (повторний запуск → 400, це нормально): покупець бачить продавця без email.
    await sellerApi.post('/api/v1/deals/', { data: { listing_id: id, buyer_id: await buyerId(api) } });
    const buyerCtx = await browser.newContext({ storageState: storageStatePath('buyer') });
    const buyerPage = await buyerCtx.newPage();
    await buyerPage.addInitScript(consentInit);
    await buyerPage.goto('/me/deals');
    const dealCard = buyerPage.locator('div.rounded-xl', { has: buyerPage.locator(`a[href="/local/${id}"]`) }).last();
    await expect(dealCard.getByText('Продавець: Користувач')).toBeVisible();
    await expect(buyerPage.locator('body')).not.toContainText('buyer@');
    await expect(buyerPage.locator('body')).not.toContainText(SELLER_EMAIL);
    await buyerCtx.close();
  });
});

async function buyerId(api: (role: 'buyer') => Promise<APIRequestContext>) {
  const resp = await (await api('buyer')).get('/api/v1/auth/profile/');
  expect(resp.status()).toBe(200);
  return (await resp.json()).id as number;
}

test('listing-buyers: гість 401, покупець 404', async ({ api, request }) => {
  const id = await activeListingId(await api('seller'));
  expect((await request.get(`/api/v1/deals/listing-buyers/${id}/`)).status()).toBe(401);
  expect((await (await api('buyer')).get(`/api/v1/deals/listing-buyers/${id}/`)).status()).toBe(404);
});
