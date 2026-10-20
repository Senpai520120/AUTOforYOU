/**
 * E2E: кабінет брокера (задача 2.4, 23-P24). Дані з e2e_seed: заявка клієнта buyer з UTM tiktok
 * і гостьова заявка зі шкідливим utm_campaign. Тести йдуть послідовно: клієнт бачить статус після брокера.
 */
import type { Page } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

test.describe.configure({ mode: 'serial' });

const CLIENT_LEAD = '[E2E] Клієнт брокера';
const XSS_LEAD = '[E2E] Гість XSS';
const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

test.beforeEach(async ({ page }) => {
  await page.addInitScript(consentInit);
});

const row = (page: Page, name: string) => page.getByTestId('broker-lead-item').filter({ hasText: name });

// Список пагінований, а інші спеки створюють заявки: засіяну заявку шукаємо за унікальним іменем,
// а не на першій сторінці.
async function searchLeads(page: Page, text: string) {
  await page.getByLabel('Ім’я або телефон').fill(text);
  await page.getByRole('button', { name: 'Знайти' }).click();
}

async function openXssLead(page: Page) {
  await page.goto('/broker/leads');
  await page.getByLabel('Ім’я або телефон').fill('Гість XSS');
  await page.getByRole('button', { name: 'Знайти' }).click();
  await expect(page).not.toHaveURL(/search=/);
  await row(page, XSS_LEAD).getByRole('link').click();
  await expect(page).toHaveURL(/\/broker\/leads\/\d+/);
}

test.describe('Брокер', () => {
  test.use({ storageState: storageStatePath('broker') });

  test('список: джерело tiktok, фільтр за джерелом, картка, «Взяти в роботу» і «Договір»', async ({ page }) => {
    await page.goto('/broker/leads');
    await expect(page.getByRole('heading', { name: 'Заявки', exact: true })).toBeVisible();
    await searchLeads(page, 'Клієнт брокера');
    await expect(row(page, CLIENT_LEAD)).toBeVisible();
    await expect(row(page, CLIENT_LEAD).getByTestId('lead-utm-source')).toHaveText('tiktok');
    await expect(page.getByTestId('new-count')).toBeVisible();

    // Фільтр за джерелом залишає цю заявку й прибирає інші.
    await page.goto('/broker/leads?utm_source=tiktok');
    await searchLeads(page, 'Клієнт брокера');
    await expect(row(page, CLIENT_LEAD)).toBeVisible();
    await searchLeads(page, 'Гість XSS');
    await expect(page.getByText('Заявок за цими умовами немає')).toBeVisible();
    await expect(row(page, XSS_LEAD)).toHaveCount(0);

    await searchLeads(page, 'Клієнт брокера');
    await row(page, CLIENT_LEAD).getByRole('link').click();
    await expect(page.getByRole('heading', { name: /AFY-\d{4}-\d+/ })).toBeVisible();
    await expect(page.getByTestId('lead-status')).toHaveText('Нова');
    // Джерело й спосіб звʼязку.
    await expect(page.getByTestId('lead-source-block')).toContainText('Точка входу');
    await expect(page.getByTestId('utm-source')).toHaveText('tiktok');
    await expect(page.getByTestId('utm-campaign')).toHaveText('spring');
    await expect(page.getByText('Спосіб звʼязку:')).toContainText('Telegram');
    await expect(page.getByRole('link', { name: '@e2e_client' })).toHaveAttribute('href', 'https://t.me/e2e_client');
    await expect(page.getByRole('link', { name: '+380671234567' })).toHaveAttribute('href', 'tel:+380671234567');
    await expect(page.getByTestId('first-response')).toContainText('ще немає');

    await page.getByRole('button', { name: 'Взяти в роботу' }).click();
    await expect(page.getByTestId('lead-status')).toHaveText('У роботі');
    await expect(page.getByTestId('first-response')).toContainText('через');

    await page.getByRole('button', { name: 'Договір', exact: true }).click();
    await expect(page.getByTestId('lead-status')).toHaveText('Договір');
    // Журнал: створення + дві зміни.
    await expect(page.getByTestId('history-item')).toHaveCount(3);
    await expect(page.getByTestId('lead-history')).toContainText('Брокер #');
  });

  test('помилка 400 при зміні статусу: зрозуміле повідомлення, статус не змінився', async ({ page }) => {
    await openXssLead(page);
    await expect(page.getByTestId('lead-status')).toHaveText('Нова');
    await page.route('**/api/v1/broker/leads/*/status/', (route) =>
      route.fulfill({
        status: 400, contentType: 'application/json',
        body: JSON.stringify({ detail: 'Перехід new -> rejected неприпустимий' }),
      }));
    await page.getByRole('button', { name: 'Відмова', exact: true }).click();
    await expect(page.getByText('Перехід new -> rejected неприпустимий')).toBeVisible();
    await expect(page.getByTestId('lead-status')).toHaveText('Нова');
  });

  test('шкідливий utm_campaign показується текстом: без діалогів і виконання скрипта', async ({ page }) => {
    const dialogs: string[] = [];
    page.on('dialog', (d) => { dialogs.push(d.message()); void d.dismiss(); });
    await openXssLead(page);
    await expect(page.getByTestId('utm-campaign')).toHaveText('<script>window.__xss=1</script>');
    expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
    expect(dialogs).toHaveLength(0);
    // <img onerror> у коментарі — теж текст: елемента немає, обробник не спрацював.
    await expect(page.getByText('<img src=x onerror=window.__xss=2>')).toBeVisible();
    await expect(page.locator('img[src="x"]')).toHaveCount(0);
    expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
    // Значення джерела не є посиланням.
    await expect(page.getByTestId('lead-source-block').getByRole('link')).toHaveCount(0);
  });

  test('шапка і /me показують «Заявки»', async ({ page }) => {
    await page.goto('/me');
    await expect(page.getByRole('link', { name: 'Заявки', exact: true }).first()).toBeVisible();
  });
});

test.describe('Клієнт (buyer)', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('бачить новий статус своєї заявки в /me/leads', async ({ page }) => {
    await page.goto('/me/leads');
    const item = page.getByTestId('lead-item').filter({ hasText: 'Toyota RAV4' });
    await expect(item.first()).toContainText('Договір');
  });

  test('шапка без «Заявки»; /broker/leads -> «Доступ обмежено», API 403', async ({ page, api }) => {
    await page.goto('/me');
    await expect(page.getByText('Покупець', { exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Заявки', exact: true })).toHaveCount(0);

    const [resp] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/v1/broker/leads/')),
      page.goto('/broker/leads'),
    ]);
    expect(resp.status()).toBe(403);
    await expect(page.getByRole('heading', { name: 'Доступ обмежено' })).toBeVisible();
    await expect(page.getByTestId('broker-lead-item')).toHaveCount(0);

    const buyerApi = await api('buyer');
    const filtered = await buyerApi.get('/api/v1/broker/leads/?utm_source=tiktok');
    expect(filtered.status()).toBe(403);
  });
});

test.describe('Гість', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('/broker/leads -> /login', async ({ page }) => {
    await page.goto('/broker/leads');
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('Мобільний @mobile', () => {
  test.use({ storageState: storageStatePath('broker') });

  test('/broker/leads на вузькому екрані без горизонтального скролу @mobile', async ({ page }) => {
    await page.goto('/broker/leads');
    await expect(row(page, CLIENT_LEAD)).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
