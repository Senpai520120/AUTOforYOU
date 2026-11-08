/**
 * E2E: скарги на оголошення (задача 4.13, B8/B9).
 * Стек e2e: C2C_ENABLED=true. Дані — e2e_seed: active «Skoda Octavia» і pending «Toyota Camry» продавця seller.
 * Реальний ліміт 429 перевіряють Django-тести (reports/tests.py): на e2e-стеку ліміти зняті E2E_RELAX_THROTTLES,
 * тут 429 — мок відповіді, перевіряється текст.
 */
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

type Item = { id: number; make: string; model: string; status?: string };

test.describe('Скарги (4.13)', () => {
  test.use({ storageState: storageStatePath('buyer') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  async function sellerListings(api: (r: 'seller') => Promise<import('@playwright/test').APIRequestContext>) {
    const seller = await api('seller');
    const body = await (await seller.get('/api/v1/local/my-listings/')).json();
    const items: Item[] = Array.isArray(body) ? body : body.results;
    const active = items.find((l) => l.make === 'Skoda' && l.model === 'Octavia');
    const pending = items.find((l) => l.make === 'Toyota' && l.model === 'Camry');
    if (!active || !pending) throw new Error('e2e_seed: немає оголошень продавця');
    return { active: active.id, pending: pending.id };
  }

  test('успіх: покупець скаржиться на активне оголошення і бачить «Скаргу подано.»', async ({ page, api }) => {
    const { active } = await sellerListings(api);
    await page.goto(`/local/${active}`);
    await page.getByRole('button', { name: 'Поскаржитися' }).click();
    const response = page.waitForResponse((r) => r.url().endsWith('/api/v1/reports/') && r.request().method() === 'POST');
    await page.getByRole('dialog').getByRole('button', { name: 'Подати скаргу' }).click();
    expect((await response).status()).toBe(201);
    await expect(page.getByText('Скаргу подано.')).toBeVisible();
  });

  test('ліміт: 429 — текст «Забагато скарг, спробуйте пізніше.»', async ({ page, api }) => {
    const { active } = await sellerListings(api);
    await page.route('**/api/v1/reports/', (route) => route.fulfill({
      status: 429, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Забагато скарг, спробуйте пізніше.' }),
    }));
    await page.goto(`/local/${active}`);
    await page.getByRole('button', { name: 'Поскаржитися' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Подати скаргу' }).click();
    await expect(page.getByRole('dialog').getByRole('alert')).toHaveText('Забагато скарг, спробуйте пізніше.');
    await expect(page.getByText('Скаргу подано.')).toHaveCount(0);
  });

  test('обхід (B9): скарга на pending і на неіснуюче — однакові 404 і тіло', async ({ api }) => {
    const { pending } = await sellerListings(api);
    const dealer = await api('dealer');
    const hidden = await dealer.post('/api/v1/reports/', { data: { listing: pending, reason: 'spam' } });
    const missing = await dealer.post('/api/v1/reports/', { data: { listing: 99999999, reason: 'spam' } });
    expect(hidden.status()).toBe(404);
    expect(missing.status()).toBe(404);
    expect(await hidden.json()).toEqual(await missing.json());
  });
});
