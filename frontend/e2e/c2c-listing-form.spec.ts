/**
 * E2E: форма оголошення частника (задача 4.2; 23-P28, 23-P31, 23-P32).
 * Стек e2e: C2C_ENABLED=true, C2C_PUBLIC_POSTING_ENABLED=true (.env.e2e). Дані — e2e_seed:
 * у seller є active «[E2E] Skoda Octavia (active)»; buyer — сторонній користувач.
 */
import path from 'path';
import type { APIRequestContext, Page } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

const FIXTURES = path.join(__dirname, 'fixtures');
const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

type OwnListing = { id: number; status: string; description: string; contact_phone: string | null };

async function sellerActiveListing(request: APIRequestContext): Promise<OwnListing> {
  const resp = await request.get('/api/v1/local/my-listings/');
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  const items: OwnListing[] = Array.isArray(body) ? body : body.results;
  const found = items.find(l => l.description.startsWith('[E2E] Skoda Octavia'));
  if (!found) throw new Error('e2e_seed: немає active-оголошення продавця');
  return found;
}

async function fillRequired(page: Page, make: string) {
  await page.getByLabel('Марка').fill(make);
  await page.getByLabel('Модель').fill('Model E2E');
  await page.getByLabel('Рік').fill('2019');
  await page.getByLabel('Пробіг, км').fill('90000');
  await page.getByLabel('Ціна').fill('12000');
  await page.getByLabel('Область').selectOption({ index: 1 });
  const city = page.getByLabel('Місто');
  await expect(city.locator('option').nth(1)).toBeAttached();
  await city.selectOption({ index: 1 });
  await page.getByLabel('Опис').fill('[E2E] Звичайний опис без контактів');
  await page.getByLabel('Контактний телефон').fill('+380501112233');
  await page.getByRole('checkbox').check();
}

test.describe('Форма оголошення (4.2): продавець', () => {
  test.use({ storageState: storageStatePath('seller') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('успіх: подача з 2 фото → «надіслано на модерацію», у кабінеті «На модерації»', async ({ page }) => {
    const make = `[E2E] Form${Date.now() % 100000}`;
    await page.goto('/local/new');
    await fillRequired(page, make);
    await page.locator('input[type=file]').setInputFiles([
      path.join(FIXTURES, 'car-1.jpg'), path.join(FIXTURES, 'car-2.jpg'),
    ]);
    await expect(page.getByText(/^2\/\d+ ·/)).toBeVisible();
    await page.getByRole('button', { name: 'Опублікувати оголошення' }).click();
    await expect(page.getByRole('heading', { name: 'Оголошення надіслано на модерацію' })).toBeVisible();
    await page.goto('/me/local-listings');
    await expect(page.getByText(make).first()).toBeVisible();
    await expect(page.getByText('На модерації').first()).toBeVisible();
  });

  test('обхід: .gif не приймається, запит завантаження не відправлено', async ({ page }) => {
    const uploads: string[] = [];
    page.on('request', r => { if (r.url().includes('/images/')) uploads.push(r.url()); });
    await page.goto('/local/new');
    await page.locator('input[type=file]').setInputFiles({
      name: 'anim.gif', mimeType: 'image/gif', buffer: Buffer.from('GIF89a\x01\x00\x01\x00\x00\x00\x00;'),
    });
    await expect(page.getByRole('alert').filter({ hasText: 'непідтримуваний формат' })).toBeVisible();
    expect(uploads).toHaveLength(0);
  });

  test('обхід: файл більший за ліміт з /local/config/ не приймається', async ({ page, request }) => {
    const config = await (await request.get('/api/v1/local/config/')).json();
    await page.goto('/local/new');
    const big = Buffer.alloc(Math.ceil(config.photo_max_size_mb * 1024 * 1024) + 1024, 0);
    await page.locator('input[type=file]').setInputFiles({ name: 'big.jpg', mimeType: 'image/jpeg', buffer: big });
    await expect(page.getByRole('alert').filter({ hasText: `більший за ${config.photo_max_size_mb} МБ` })).toBeVisible();
  });

  test('успіх: зміна лише телефону лишає «Активне», телефон бачить покупець', async ({ page, browser }) => {
    const listing = await sellerActiveListing(page.request);
    await page.goto(`/local/${listing.id}/edit`);
    const phone = page.getByLabel('Контактний телефон');
    await expect(phone).toHaveValue(/.*/);
    await phone.fill('+380671234567');
    await page.getByRole('button', { name: 'Зберегти зміни' }).click();
    await expect(page).toHaveURL(new RegExp(`/local/${listing.id}$`));
    const after = await (await page.request.get(`/api/v1/local/my-listings/${listing.id}/`)).json();
    expect(after.status).toBe('active');
    expect(after.contact_phone).toBe('+380671234567');

    const buyer = await browser.newContext({ storageState: storageStatePath('buyer') });
    const contact = await buyer.request.get(`/api/v1/local/listings/${listing.id}/contact/`);
    expect(contact.status()).toBe(200);
    expect((await contact.json()).contact_phone).toBe('+380671234567');
    await buyer.close();
  });

  test('обхід: порожній телефон при редагуванні → помилка під полем, телефон не стерто', async ({ page }) => {
    const listing = await sellerActiveListing(page.request);
    await page.goto(`/local/${listing.id}/edit`);
    await page.getByLabel('Контактний телефон').fill('');
    await page.getByRole('button', { name: 'Зберегти зміни' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Вкажіть телефон' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Зберегти зміни' })).toBeEnabled();
    const after = await (await page.request.get(`/api/v1/local/my-listings/${listing.id}/`)).json();
    expect(after.contact_phone).not.toBe('');
  });

  test.fixme('4.2 → окремий e2e-стек з ANTISPAM_MODE=hard: телефон в описі → помилка під «Опис», екрану успіху немає', async () => {});
  test.fixme('4.2 → повторна скарга (23-P36): у модалці текст сервера, а не «Не вдалося подати скаргу»', async () => {});
});

test.describe('Форма оголошення (4.2): сторонній', () => {
  test.use({ storageState: storageStatePath('buyer') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('обхід: покупець на /edit чужого оголошення бачить «не власник», полів немає', async ({ page, browser }) => {
    const seller = await browser.newContext({ storageState: storageStatePath('seller') });
    const listing = await sellerActiveListing(seller.request);
    await seller.close();
    await page.goto(`/local/${listing.id}/edit`);
    await expect(page.getByText('Оголошення не знайдено або ви не власник')).toBeVisible();
    await expect(page.getByLabel('Марка')).toHaveCount(0);
  });
});
