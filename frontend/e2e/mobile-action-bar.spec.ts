/**
 * E2E: нижня панель дій на мобільній картці C2C (задача 6.6).
 * Проєкти mobile-chrome (Pixel 7) і mobile-safari (iPhone 13) — тег @mobile; десктоп — окремий тест без тегу.
 * Стек e2e: C2C_ENABLED=true, капча honeypot. Дані — e2e_seed: active «Skoda Octavia» продавця seller
 * з номером +380671112233. Гілка «картка лота» не перевіряється: каталог заморожено (2.8).
 */
import type { APIRequestContext, Page } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

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

const bar = (page: Page) => page.getByRole('navigation', { name: 'Дії з оголошенням' });

test.describe('Мобільна панель: гість @mobile', () => {
  test.use({ storageState: GUEST });

  test('«Подзвонити» відкриває ту саму капчу, після перевірки кнопка стає tel: @mobile', async ({ page, api }) => {
    await page.addInitScript(consentInit);
    const { id, phone: PHONE } = await seededListing(api);
    await page.goto(`/local/${id}`);
    await expect(bar(page)).toBeVisible();
    await bar(page).getByRole('button', { name: /Подзвонити/ }).click();
    const reveal = page.getByTestId('guest-phone').getByRole('button', { name: 'Показати номер' });
    await expect(reveal).toBeVisible();
    await expect(page.getByTestId('guest-phone')).toHaveCount(1); // одна капча, не дві
    await expect(reveal).toBeEnabled({ timeout: 10_000 });
    await reveal.click();
    await expect(bar(page).getByRole('link', { name: 'Подзвонити' })).toHaveAttribute('href', `tel:${PHONE}`);
  });

  test('ліміт 429: номер не показано, текст ліміту, кнопка панелі лишається кнопкою @mobile', async ({ page, api }) => {
    await page.addInitScript(consentInit);
    const { id, phone: PHONE } = await seededListing(api);
    await page.route(`**/api/v1/local/listings/${id}/contact/`, (route) => route.request().method() === 'POST'
      ? route.fulfill({
        status: 429, contentType: 'application/json',
        body: JSON.stringify({ detail: 'Ліміт переглядів телефонів на сьогодні вичерпано' }),
      })
      : route.continue());
    await page.goto(`/local/${id}`);
    await bar(page).getByRole('button', { name: /Подзвонити/ }).click();
    const reveal = page.getByTestId('guest-phone').getByRole('button', { name: 'Показати номер' });
    await expect(reveal).toBeEnabled({ timeout: 10_000 });
    await reveal.click();
    await expect(page.getByTestId('guest-phone').getByRole('alert')).toHaveText('Ліміт переглядів телефонів на сьогодні вичерпано');
    await expect(page.getByText(PHONE)).toHaveCount(0);
    await expect(bar(page).getByRole('link', { name: 'Подзвонити' })).toHaveCount(0);
  });

  test('банер cookie: панель над ним і клікабельна, після вибору опускається донизу @mobile', async ({ page, api }) => {
    const { id } = await seededListing(api);
    await page.goto(`/local/${id}`);
    const banner = page.getByRole('dialog', { name: 'Налаштування файлів cookie' });
    await expect(banner).toBeVisible();
    await expect(bar(page)).toBeVisible();
    const barBox = (await bar(page).boundingBox())!;
    const bannerBox = (await banner.boundingBox())!;
    expect(barBox.y + barBox.height).toBeLessThanOrEqual(bannerBox.y + 1);
    // кнопка панелі не перекрита: елемент у її центрі — всередині панелі
    const call = bar(page).getByRole('button', { name: /Подзвонити/ });
    const c = (await call.boundingBox())!;
    const hit = await page.evaluate(([x, y]) => !!document.elementFromPoint(x, y)?.closest('[data-testid="mobile-action-bar"]'),
      [c.x + c.width / 2, c.y + c.height / 2]);
    expect(hit).toBe(true);

    await banner.getByRole('button', { name: 'Лише необхідні' }).click();
    await expect(banner).toBeHidden();
    const viewport = page.viewportSize()!;
    await expect.poll(async () => {
      const b = (await bar(page).boundingBox())!;
      return Math.round(viewport.height - (b.y + b.height));
    }).toBeLessThanOrEqual(1);
  });

  test('без горизонтального скролу і кнопки не нижчі за 44 px @mobile', async ({ page, api }) => {
    await page.addInitScript(consentInit);
    const { id } = await seededListing(api);
    await page.goto(`/local/${id}`);
    await expect(bar(page)).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    for (const el of await bar(page).locator('a, button').all()) {
      expect((await el.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  });
});

test.describe('Мобільна панель: покупець @mobile', () => {
  test.use({ storageState: storageStatePath('buyer') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('«Подзвонити» — номер одразу; лічильник 500 не заважає @mobile', async ({ page, api }) => {
    const bodies: unknown[] = [];
    await page.route('**/api/v1/metrics/event/', (route) => {
      bodies.push(route.request().postDataJSON());
      return route.fulfill({ status: 500, body: '' });
    });
    const { id, phone: PHONE } = await seededListing(api);
    await page.goto(`/local/${id}`);
    await bar(page).getByRole('button', { name: /Подзвонити/ }).click();
    await expect(bar(page).getByRole('link', { name: 'Подзвонити' })).toHaveAttribute('href', `tel:${PHONE}`);
    // лічильник без ПДн: рівно ключ, без номера й id оголошення
    await expect.poll(() => bodies).toContainEqual({ key: 'mobile_bar_click' });
    for (const b of bodies) expect(Object.keys(b as object)).toEqual(['key']);
  });

  test('«Написати» відкриває діалог поверх панелі; фокус у полі ховає панель @mobile', async ({ page, api }) => {
    const { id } = await seededListing(api);
    await page.goto(`/local/${id}`);
    await bar(page).getByRole('button', { name: 'Написати' }).click();
    const field = page.getByLabel('Ваше перше повідомлення');
    await expect(field).toBeVisible();
    // діалог на весь екран, а не затиснутий у панелі
    const dialogBox = (await page.getByRole('dialog').locator('..').boundingBox())!; // підкладка модалки
    expect(dialogBox.height).toBeGreaterThan(page.viewportSize()!.height / 2);
    await field.focus();
    await expect(bar(page)).toBeHidden();
    await field.blur();
    await expect(bar(page)).toBeVisible();
    // модалка вище за панель: точка панелі накрита підкладкою модалки
    const b = (await bar(page).boundingBox())!;
    const coveredByModal = await page.evaluate(([x, y]) => !document.elementFromPoint(x, y)?.closest('[data-testid="mobile-action-bar"]'),
      [b.x + 10, b.y + b.height / 2]);
    expect(coveredByModal).toBe(true);
  });
});

test.describe('Мобільна панель: власник @mobile', () => {
  test.use({ storageState: storageStatePath('seller') });

  test('на своєму оголошенні панелі немає @mobile', async ({ page, api }) => {
    await page.addInitScript(consentInit);
    const { id } = await seededListing(api);
    await page.goto(`/local/${id}`);
    await expect(page.getByRole('link', { name: 'Редагувати' })).toBeVisible();
    await expect(bar(page)).toHaveCount(0);
  });
});

test.describe('Мобільна панель: десктоп', () => {
  test.use({ storageState: GUEST });

  test('на десктопі панель не показується', async ({ page, api }) => {
    await page.addInitScript(consentInit);
    const { id } = await seededListing(api);
    await page.goto(`/local/${id}`);
    await expect(page.getByRole('button', { name: 'Показати телефон' })).toBeVisible();
    await expect(bar(page)).toBeHidden();
  });
});
