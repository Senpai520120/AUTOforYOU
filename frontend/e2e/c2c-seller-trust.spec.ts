/**
 * E2E: довіра до продавця і банер передоплати (задача 8.6).
 * Стек e2e: C2C_ENABLED=true. Дані — e2e_seed: active «Skoda Octavia» продавця seller,
 * active «Ford Focus» верифікованого дилера dealer (seller_type=dealer), діалог buyer–seller.
 * Логіку «дилер лише при верифікації» і відкликання перевіряють Django-тести (local_listings/tests_seller_trust.py).
 */
import type { APIRequestContext } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

type Item = { id: number; make: string; model: string; status: string };

async function activeListing(ctx: APIRequestContext, make: string, model: string): Promise<number> {
  const body = await (await ctx.get('/api/v1/local/my-listings/')).json();
  const items: Item[] = Array.isArray(body) ? body : body.results;
  const found = items.find((l) => l.make === make && l.model === model && l.status === 'active');
  if (!found) throw new Error(`e2e_seed: немає активного оголошення ${make} ${model}`);
  return found.id;
}

test.describe('Довіра до продавця (8.6)', () => {
  test.use({ storageState: storageStatePath('buyer') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('успіх: банер, «на сайті з …» і перехід на сторінку продавця з його оголошеннями', async ({ page, api }) => {
    const id = await activeListing(await api('seller'), 'Skoda', 'Octavia');
    await page.goto(`/local/${id}`);

    const banner = page.getByTestId('scam-warning');
    await expect(banner).toContainText('передоплату');
    await expect(banner.getByRole('link', { name: 'Правила безпечної угоди' })).toHaveAttribute('href', '/rules');

    const block = page.getByTestId('seller-block');
    await expect(block).toContainText(/на сайті з \S+ \d{4}/);
    await expect(page.getByTestId('verified-dealer')).toHaveCount(0);
    await block.getByRole('link', { name: 'Усі оголошення продавця' }).click();

    await expect(page).toHaveURL(/\/sellers\/\d+$/);
    const profile = page.getByTestId('seller-profile');
    await expect(profile).toContainText(/на сайті з \S+ \d{4}/);
    await expect(profile).toContainText('Підтверджених угод:');
    await expect(page.getByRole('heading', { name: /Skoda Octavia/ })).toBeVisible();
  });

  test('успіх: оголошення верифікованого дилера — бейдж «Перевірений дилер» на сторінці і в картці', async ({ page, api }) => {
    const id = await activeListing(await api('dealer'), 'Ford', 'Focus');
    await page.goto(`/local/${id}`);
    await expect(page.getByTestId('verified-dealer')).toHaveText('✓ Перевірений дилер');
    await page.getByRole('link', { name: 'Усі оголошення продавця' }).click();
    await expect(page.getByTestId('seller-profile').getByTestId('verified-dealer')).toBeVisible();
    await expect(page.locator('article').getByTestId('verified-dealer')).toHaveCount(1);
  });

  test('успіх: банер у вікні першого повідомлення і в діалозі над полем вводу', async ({ page, api }) => {
    const id = await activeListing(await api('seller'), 'Skoda', 'Octavia');
    await page.goto(`/local/${id}`);
    await page.getByRole('button', { name: 'Написати продавцю' }).first().click();
    await expect(page.getByRole('dialog').getByTestId('scam-warning')).toBeVisible();
    await page.getByRole('dialog').getByRole('button', { name: 'Скасувати' }).click();

    await page.goto('/me/messages');
    await page.getByRole('listitem').getByRole('button').first().click();
    await expect(page.getByRole('textbox', { name: 'Повідомлення' })).toBeVisible();
    await expect(page.getByTestId('scam-warning')).toBeVisible();
  });

  test('обхід: порожній текст банера в налаштуваннях — банера немає', async ({ page, api }) => {
    await page.route('**/api/v1/site-settings/', async (route) => {
      const res = await route.fetch();
      const json = await res.json();
      await route.fulfill({ response: res, json: { ...json, prepayment_warning_text: '' } });
    });
    const id = await activeListing(await api('seller'), 'Skoda', 'Octavia');
    // Банер з'являється лише після відповіді site-settings: дочекатися її, тоді перевіряти відсутність.
    const settings = page.waitForResponse((r) => r.url().endsWith('/api/v1/site-settings/'));
    await page.goto(`/local/${id}`);
    expect((await (await settings).json()).prepayment_warning_text).toBe('');
    await expect(page.getByTestId('seller-block')).toBeVisible();
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null)))));
    await expect(page.getByTestId('scam-warning')).toHaveCount(0);
  });

  test('обхід: /sellers/999999 — «Продавця не знайдено», без падіння', async ({ page }) => {
    await page.goto('/sellers/999999');
    await expect(page.getByRole('main').getByText('Продавця не знайдено', { exact: true }).first()).toBeVisible();
    await expect(page.getByTestId('seller-profile')).toHaveCount(0);
  });

  test('обхід: у HTML сторінки продавця і оголошення немає email і телефону', async ({ page, api }) => {
    const id = await activeListing(await api('seller'), 'Skoda', 'Octavia');
    const detail = await (await page.request.get(`/api/v1/local/listings/${id}/`)).json();
    expect(detail.seller_id).toBeGreaterThan(0);
    for (const [url, marker] of [[`/local/${id}`, 'seller-block'], [`/sellers/${detail.seller_id}`, 'seller-profile']]) {
      const res = await page.request.get(url);
      expect(res.status()).toBe(200);
      const html = await res.text();
      // Підвал містить support@e2e.test — шукаємо саме дані продавця: email, contact_phone, verified_phone.
      expect(html).toContain(`data-testid="${marker}"`); // блок продавця справді відрендерено на сервері
      expect(html).not.toContain('seller@e2e.test');
      expect(html).not.toContain('671112233');
      expect(html).not.toContain('670000001');
    }
  });
});

test.describe('Тип продавця визначає сервер (8.6)', () => {
  test.use({ storageState: storageStatePath('seller') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('обхід: звичайний продавець шле seller_type=dealer — оголошення private; у формі вибору типу немає', async ({ page, api }) => {
    const seller = await api('seller');
    const cities = await (await seller.get('/api/v1/local/cities/?q=вінниц')).json();
    const resp = await seller.post('/api/v1/local/listings/', {
      data: {
        make: 'Skoda', model: '[E2E] Самозваний дилер', year: 2015, mileage_km: 1, price: '1000', currency: 'USD',
        fuel_type: 'petrol', transmission: 'manual', body_type: 'sedan', condition: 'used',
        region: cities[0].region, city: cities[0].id, description: '[E2E] seller_type', contact_phone: '+380501112295',
        agreed_to_rules: true, legal_confirmed: true, seller_type: 'dealer',
      },
    });
    expect(resp.status()).toBe(201);
    const created = await resp.json();
    expect(created.seller_type).toBe('private');
    const mine = await (await seller.get(`/api/v1/local/my-listings/${created.id}/`)).json();
    expect(mine.seller_type).toBe('private');

    await page.goto('/local/new');
    await expect(page.getByLabel('Марка')).toBeVisible();
    await expect(page.getByLabel(/Тип продавця/)).toHaveCount(0);
    await expect(page.getByRole('option', { name: 'Дилер' })).toHaveCount(0);
    await expect(page.getByTestId('posting-as-dealer')).toHaveCount(0);
  });

  test('успіх: верифікованому дилеру — рядок «Ви публікуєте як перевірений дилер»', async ({ page }) => {
    // dealer у сиді без підтвердженого телефону (4.10) і бачить крок телефону замість форми;
    // тут профіль продавця (телефон підтверджено) підміняється прапорцем дилера — перевіряється саме рядок форми.
    await page.route('**/api/v1/auth/profile/', async (route) => {
      if (route.request().method() !== 'GET') return route.continue();
      const res = await route.fetch();
      const json = await res.json();
      await route.fulfill({ response: res, json: { ...json, is_verified_dealer: true, role: 'dealer' } });
    });
    await page.goto('/local/new');
    await expect(page.getByTestId('posting-as-dealer')).toHaveText('✓ Ви публікуєте як перевірений дилер');
  });
});
