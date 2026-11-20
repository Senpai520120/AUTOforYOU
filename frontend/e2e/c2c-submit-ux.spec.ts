/**
 * E2E: подача оголошення, UX (задача 10.25; B4-B6, B10).
 * Стек e2e: C2C включено; сід: seller з підтвердженим номером, SiteSettings.listing_moderation_hours = 24.
 */
import type { Page } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';
import { SEED_LISTING_PHONE, SELLER_VERIFIED_PHONE } from './helpers/listing-form';

const GUEST = { cookies: [], origins: [] };
const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const NOTICE = 'Щоб подати оголошення, увійдіть або зареєструйтесь. Реєстрація безкоштовна.';

test.describe('Пояснення на вході при next=/local/new', () => {
  test.use({ storageState: GUEST });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  for (const path of ['/login', '/register']) {
    test(`${path}?next=/local/new: пояснення видно, форма на місці`, async ({ page }) => {
      await page.goto(`${path}?next=/local/new`);
      await expect(page.getByText(NOTICE)).toBeVisible();
      await expect(page.getByLabel('Email')).toBeVisible();
    });

    test(`обхід: ${path} без next або з чужим next — пояснення немає`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByLabel('Email')).toBeVisible();
      await expect(page.getByText(NOTICE)).toHaveCount(0);
      await page.goto(`${path}?next=//evil.example`);
      await expect(page.getByLabel('Email')).toBeVisible();
      await expect(page.getByText(NOTICE)).toHaveCount(0);
    });
  }

  test('посилання між входом і реєстрацією зберігають next', async ({ page }) => {
    await page.goto('/login?next=/local/new');
    // У шапці теж є «Реєстрація» (без next) — перевіряємо посилання в основному блоці.
    await expect(page.getByRole('main').getByRole('link', { name: 'Реєстрація' })).toHaveAttribute('href', /\/register\?next=%2Flocal%2Fnew/);
    await page.goto('/register?next=/local/new');
    await expect(page.getByRole('link', { name: 'Увійти' })).toHaveAttribute('href', /\/login\?next=%2Flocal%2Fnew/);
  });
});

const TERM = 'Орієнтовний строк модерації — до 24 год.';

async function openForm(page: Page) {
  await page.addInitScript(consentInit);
  await page.goto('/local/new');
  await expect(page.getByLabel('Марка')).toBeVisible();
}

test.describe('Форма /local/new: кнопка, строк, телефон', () => {
  test.use({ storageState: storageStatePath('seller') });

  test('кнопка «Надіслати на модерацію» і строк із налаштувань', async ({ page }) => {
    await openForm(page);
    await expect(page.getByRole('button', { name: 'Надіслати на модерацію' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Опублікувати оголошення' })).toHaveCount(0);
    await expect(page.getByTestId('moderation-term')).toHaveText(TERM);
  });

  test('обхід: порожній строк в налаштуваннях — рядка про строк немає', async ({ page }) => {
    await page.route('**/api/v1/site-settings/', async (route) => {
      const res = await route.fetch();
      await route.fulfill({ response: res, json: { ...(await res.json()), listing_moderation_hours: null } });
    });
    const settings = page.waitForResponse((r) => r.url().endsWith('/api/v1/site-settings/'));
    await openForm(page);
    expect((await (await settings).json()).listing_moderation_hours).toBeNull();
    await expect(page.getByRole('button', { name: 'Надіслати на модерацію' })).toBeVisible();
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null)))));
    await expect(page.getByTestId('moderation-term')).toHaveCount(0);
  });

  test('підтверджений seller: номер підставлено, підказка про Telegram і /unlink', async ({ page }) => {
    await openForm(page);
    const phone = page.getByLabel('Контактний телефон');
    await expect(phone).toHaveValue('+380670000001');
    await expect(phone).not.toBeEditable();
    const hint = page.getByTestId('phone-hint');
    await expect(hint).toContainText('Номер з вашого підтвердженого Telegram');
    await expect(hint).toContainText('/unlink');
    await expect(hint.getByRole('link', { name: '«Telegram»' })).toHaveAttribute('href', '/me/telegram');
  });
});

test.describe('Нижня панель картки: капча гостя @mobile', () => {
  test.use({ storageState: GUEST });

  test('«Подзвонити» при непройденій капчі: прокрутка і фокус на блок перевірки @mobile', async ({ page, api }) => {
    await page.addInitScript(consentInit);
    const seller = await api('seller');
    const body = await (await seller.get('/api/v1/local/my-listings/')).json();
    const items: { id: number; description: string }[] = Array.isArray(body) ? body : body.results;
    const found = items.find((l) => l.description.startsWith('[E2E] Skoda Octavia (active)'));
    if (!found) throw new Error('e2e_seed: немає active-оголошення Skoda Octavia');
    await page.goto(`/local/${found.id}`);
    await page.getByRole('navigation', { name: 'Дії з оголошенням' }).getByRole('button', { name: /Подзвонити/ }).click();
    const box = page.getByTestId('guest-phone');
    await expect(box).toBeVisible();
    await expect(box).toBeFocused();
    await expect(box).toBeInViewport();
  });
});

test.describe('/sellers/[id]: без ПДн', () => {
  test.use({ storageState: GUEST });

  test('у HTML сторінки продавця немає телефону і email', async ({ page, request }) => {
    const list = await (await request.get('/api/v1/local/listings/')).json();
    const detail = await (await request.get(`/api/v1/local/listings/${list.results[0].id}/`)).json();
    const res = await page.request.get(`/sellers/${detail.seller_id}`);
    expect(res.status()).toBe(200);
    const html = await res.text();
    expect(html).toContain('data-testid="seller-profile"');
    // Підвал містить публічний телефон сайту (SiteSettings, e2e_seed: +380500000000) — це не ПДн продавця.
    // Тому: у блоці <main> телефонів немає зовсім, а в усьому HTML немає номерів продавця і його email.
    const main = html.match(/<main[\s\S]*?<\/main>/)?.[0] ?? '';
    expect(main).toContain('data-testid="seller-profile"');
    expect(main).not.toMatch(/\+380\d{9}/);
    for (const secret of [SELLER_VERIFIED_PHONE, SELLER_VERIFIED_PHONE.slice(1), SEED_LISTING_PHONE,
      SEED_LISTING_PHONE.slice(1), 'seller@e2e.test', 'seller@']) {
      expect(html).not.toContain(secret);
    }
  });
});
