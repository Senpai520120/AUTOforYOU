/**
 * E2E: переписка та сповіщення (задача 4.7; 23-P37, 23-P39).
 * Стек e2e: C2C_ENABLED=true, C2C_PUBLIC_POSTING_ENABLED=true. Дані — e2e_seed:
 * active «[E2E] Skoda Octavia» у seller, діалог buyer↔seller; dealer — сторонній.
 */
import type { APIRequestContext } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

async function sellerActiveListingId(request: APIRequestContext): Promise<number> {
  const body = await (await request.get('/api/v1/local/my-listings/')).json();
  const items: { id: number; description: string }[] = Array.isArray(body) ? body : body.results;
  const found = items.find(l => l.description.startsWith('[E2E] Skoda Octavia'));
  if (!found) throw new Error('e2e_seed: немає active-оголошення продавця');
  return found.id;
}

test.describe('Переписка (4.7)', () => {
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('успіх: покупець пише продавцю, продавець відповідає, покупець бачить відповідь', async ({ browser }) => {
    const sellerCtx = await browser.newContext({ storageState: storageStatePath('seller') });
    const listingId = await sellerActiveListingId(sellerCtx.request);
    const buyerCtx = await browser.newContext({ storageState: storageStatePath('buyer') });
    await buyerCtx.addInitScript(consentInit);
    await sellerCtx.addInitScript(consentInit);
    const buyer = await buyerCtx.newPage();
    const stamp = Date.now() % 100000;

    await buyer.goto(`/local/${listingId}`);
    await buyer.getByRole('button', { name: 'Написати продавцю' }).click();
    await buyer.getByLabel('Ваше перше повідомлення').fill(`[E2E] Питання ${stamp}`);
    await buyer.getByRole('button', { name: 'Надіслати' }).click();
    await expect(buyer).toHaveURL(/\/me\/messages\?conv=\d+/);
    const convId = new URL(buyer.url()).searchParams.get('conv');

    const seller = await sellerCtx.newPage();
    await seller.goto(`/me/messages?conv=${convId}`);
    await expect(seller.locator('p', { hasText: `[E2E] Питання ${stamp}` })).toBeVisible();
    await seller.getByRole('textbox', { name: 'Повідомлення' }).fill(`[E2E] Відповідь ${stamp}`);
    await seller.getByRole('button', { name: 'Надіслати' }).click();
    await expect(seller.locator('p', { hasText: `[E2E] Відповідь ${stamp}` })).toBeVisible();

    await buyer.reload();
    await expect(buyer.locator('p', { hasText: `[E2E] Відповідь ${stamp}` })).toBeVisible();
    await buyerCtx.close();
    await sellerCtx.close();
  });

  test('обхід: на своєму оголошенні у продавця немає «Написати продавцю»', async ({ browser }) => {
    const sellerCtx = await browser.newContext({ storageState: storageStatePath('seller') });
    await sellerCtx.addInitScript(consentInit);
    const listingId = await sellerActiveListingId(sellerCtx.request);
    const page = await sellerCtx.newPage();
    await page.goto(`/local/${listingId}`);
    await expect(page.getByRole('link', { name: 'Редагувати' }).or(page.getByRole('button', { name: 'Редагувати' })).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Написати продавцю' })).toHaveCount(0);
    await sellerCtx.close();
  });

  test('обхід: сторонній на ?conv=<чужий> бачить «Немає доступу до цієї розмови»', async ({ browser }) => {
    const buyerCtx = await browser.newContext({ storageState: storageStatePath('buyer') });
    const convs = await (await buyerCtx.request.get('/api/v1/messages/conversations/')).json();
    const conv = convs.results[0];
    await buyerCtx.close();

    const dealerCtx = await browser.newContext({ storageState: storageStatePath('dealer') });
    await dealerCtx.addInitScript(consentInit);
    const page = await dealerCtx.newPage();
    await page.goto(`/me/messages?conv=${conv.id}`);
    await expect(page.getByText('Немає доступу до цієї розмови')).toBeVisible();
    if (conv.last_message_text) await expect(page.getByText(conv.last_message_text)).toHaveCount(0);
    await dealerCtx.close();
  });

  test.fixme('4.7 → окремий e2e-стек з ANTISPAM_MODE=hard: телефон у повідомленні → помилка під полем, текст лишився', async () => {});
});

test.describe('Сповіщення (4.7)', () => {
  test.use({ storageState: storageStatePath('seller') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('обхід: /notifications/ → 500: видима помилка і «Спробувати ще раз», а не порожній список', async ({ page }) => {
    await page.route('**/api/v1/notifications/?page=*', route => route.fulfill({
      status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'boom' }),
    }));
    await page.goto('/me/notifications');
    await expect(page.getByRole('button', { name: 'Спробувати ще раз' })).toBeVisible();
    await expect(page.getByText('Немає сповіщень.')).toHaveCount(0);
  });

  test('успіх: після нового повідомлення є непрочитане, «Позначити всі прочитаними» прибирає його', async ({ page, browser }) => {
    const listingId = await sellerActiveListingId(page.request);
    const buyerCtx = await browser.newContext({ storageState: storageStatePath('buyer') });
    await buyerCtx.addInitScript(consentInit);
    const buyer = await buyerCtx.newPage();
    await buyer.goto(`/local/${listingId}`);
    await buyer.getByRole('button', { name: 'Написати продавцю' }).click();
    await buyer.getByLabel('Ваше перше повідомлення').fill('[E2E] Для сповіщення');
    await buyer.getByRole('button', { name: 'Надіслати' }).click();
    await expect(buyer).toHaveURL(/\/me\/messages\?conv=\d+/);
    await buyerCtx.close();

    await page.goto('/me/notifications');
    await expect(page.getByText(/Нове повідомлення від/).first()).toBeVisible();
    await page.getByRole('button', { name: 'Позначити всі прочитаними' }).click();
    await expect(page.getByRole('button', { name: 'Позначити всі прочитаними' })).toHaveCount(0);
  });
});
