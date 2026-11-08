/**
 * E2E: телефон продавця (задача 4.5a, 23-P30, F3.2).
 * Стек e2e: C2C_ENABLED=true, капча — honeypot (TURNSTILE_* порожні), PHONE_LOG_IP_SALT задано в .env.e2e.
 * Дані — e2e_seed: active «[E2E] Skoda Octavia (active)» продавця seller з номером (поточний номер — з кабінету).
 * Реальний добовий ліміт гостя (429) і журнал в адмінці перевіряють Django-тести
 * (local_listings/tests_contact.py): на e2e-стеку ліміти зняті E2E_RELAX_THROTTLES, а ролі модератора немає.
 */
import type { APIRequestContext, Page, Request, Response } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';
import { expectNoRequest } from './helpers/network';

const GUEST = { cookies: [], origins: [] };
const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

/**
 * Саме оголошення з e2e_seed (маркер в описі): інші спеки повного прогону створюють свої «Skoda Octavia»,
 * а c2c-listing-form міняє номер цього оголошення — тому номер беремо поточний, з кабінету продавця.
 */
async function seededListing(api: (role: 'seller') => Promise<APIRequestContext>): Promise<{ id: number; phone: string }> {
  const seller = await api('seller');
  const body = await (await seller.get('/api/v1/local/my-listings/')).json();
  const items: { id: number; description: string }[] = Array.isArray(body) ? body : body.results;
  const found = items.find((l) => l.description.startsWith('[E2E] Skoda Octavia (active)'));
  if (!found) throw new Error('e2e_seed: немає active-оголошення Skoda Octavia');
  const detail = await (await seller.get(`/api/v1/local/my-listings/${found.id}/`)).json();
  if (!detail.contact_phone) throw new Error('e2e_seed: у оголошення немає номера');
  return { id: found.id, phone: detail.contact_phone };
}

const isGuestContactPost = (id: number) => (r: Request) =>
  r.url().endsWith(`/api/v1/local/listings/${id}/contact/`) && r.method() === 'POST';
const guestContactResponse = (id: number) => (r: Response) => isGuestContactPost(id)(r.request());

async function openGuestCaptcha(page: Page, id: number) {
  await page.goto(`/local/${id}`);
  await page.getByRole('button', { name: 'Показати телефон' }).click();
  return page.getByRole('button', { name: 'Показати номер' });
}

test.describe('Телефон: вхід (4.5a)', () => {
  test.use({ storageState: storageStatePath('buyer') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('успіх: покупець натискає «Показати телефон» — номер видно, посилання tel:', async ({ page, api }) => {
    const { id, phone: PHONE } = await seededListing(api);
    await page.goto(`/local/${id}`);
    await page.getByRole('button', { name: 'Показати телефон' }).click();
    await expect(page.getByRole('link', { name: PHONE })).toHaveAttribute('href', `tel:${PHONE}`);
  });
});

test.describe('Телефон: гість після капчі (4.5a, F3.2)', () => {
  test.use({ storageState: GUEST });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('успіх: гість проходить перевірку і бачить номер без входу', async ({ page, api }) => {
    const { id, phone: PHONE } = await seededListing(api);
    const reveal = await openGuestCaptcha(page, id);
    // honeypot: кнопка активна лише після мінімального часу заповнення
    await expect(reveal).toBeEnabled({ timeout: 10_000 });
    const response = page.waitForResponse(guestContactResponse(id));
    await reveal.click();
    expect((await response).status()).toBe(200);
    await expect(page.getByRole('link', { name: PHONE })).toHaveAttribute('href', `tel:${PHONE}`);
  });

  test('обхід: номера немає в HTML сторінки і до перевірки запит не йде', async ({ page, api }) => {
    const { id, phone: PHONE } = await seededListing(api);
    const html = await (await page.request.get(`/local/${id}`)).text();
    expect(html).not.toContain(PHONE);
    expect(html).not.toContain(PHONE.replace(/\D/g, '').slice(-9));

    await expectNoRequest(page, isGuestContactPost(id), async () => {
      const reveal = await openGuestCaptcha(page, id);
      await expect(reveal).toBeDisabled(); // токена капчі ще немає
    }, 1500);
    await expect(page.getByText(PHONE)).toHaveCount(0);
  });

  test('обхід: заповнене honeypot-поле — помилка перевірки, номер не показано', async ({ page, api }) => {
    const { id, phone: PHONE } = await seededListing(api);
    const reveal = await openGuestCaptcha(page, id);
    // Бот заповнює приховане поле; людина його не бачить.
    await page.locator('input[name="website"]').fill('http://spam', { force: true });
    await expect(reveal).toBeEnabled({ timeout: 10_000 });
    const response = page.waitForResponse(guestContactResponse(id));
    await reveal.click();
    expect((await response).status()).toBe(400);
    await expect(page.getByTestId('guest-phone').getByRole('alert')).toHaveText('Не вдалося пройти перевірку. Спробуйте ще раз.');
    await expect(page.getByText(PHONE)).toHaveCount(0);
  });

  test('ліміт: 429 від сервера — текст про добовий ліміт, номер не показано', async ({ page, api }) => {
    const { id, phone: PHONE } = await seededListing(api);
    await page.route(`**/api/v1/local/listings/${id}/contact/`, (route) => route.request().method() === 'POST'
      ? route.fulfill({
        status: 429, contentType: 'application/json',
        body: JSON.stringify({ detail: 'Ліміт переглядів телефонів на сьогодні вичерпано' }),
      })
      : route.continue());
    const reveal = await openGuestCaptcha(page, id);
    await expect(reveal).toBeEnabled({ timeout: 10_000 });
    await reveal.click();
    await expect(page.getByTestId('guest-phone').getByRole('alert')).toHaveText('Ліміт переглядів телефонів на сьогодні вичерпано');
    await expect(page.getByText(PHONE)).toHaveCount(0);
  });
});
