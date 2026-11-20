/**
 * E2E: ліміти подачі та «не в розшуку» (задача 8.5).
 * Стек e2e: C2C_ENABLED=true, подача відкрита, ліміти DRF зняті (E2E_RELAX_THROTTLES), ANTISPAM_MODE — з .env.e2e.
 * Реальний 429 і режим hard перевіряють Django-тести (local_listings/tests_submission.py); тут 429 — мок відповіді.
 * seller — з підтвердженим телефоном (e2e_seed).
 */
import path from 'path';
import type { Page } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

async function fillForm(page: Page, description = '[E2E] Ліміти подачі') {
  await page.getByLabel('Марка').fill('Skoda');
  await page.getByLabel('Модель').fill('[E2E] Ліміти');
  await page.getByLabel('Рік').fill('2016');
  await page.getByLabel('Пробіг, км').fill('140000');
  await page.getByLabel('Ціна').fill('7500');
  await page.getByRole('combobox', { name: 'Населений пункт *' }).fill('Вінниц');
  await page.getByRole('option', { name: /^Вінниця/ }).click();
  await page.getByLabel('Опис').fill(description);
  await page.getByLabel('Контактний телефон').fill('+380501112294');
  await page.locator('input[type=file]').setInputFiles(path.join(__dirname, 'fixtures', 'car-1.jpg'));
}

test.describe('Подача: ліміти і підтвердження (8.5)', () => {
  test.use({ storageState: storageStatePath('seller') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('успіх: обидві відмітки — оголошення надіслано на модерацію', async ({ page }) => {
    await page.goto('/local/new');
    await fillForm(page);
    await page.getByRole('checkbox', { name: /правилами/ }).check();
    await page.getByRole('checkbox', { name: /не в розшуку/ }).check();
    await page.getByRole('button', { name: 'Надіслати на модерацію' }).click();
    await expect(page.getByRole('heading', { name: 'Оголошення надіслано на модерацію' })).toBeVisible();
  });

  test('обхід: без «не в розшуку» кнопка неактивна; прямий POST без відмітки → 400', async ({ page, api }) => {
    await page.goto('/local/new');
    await fillForm(page);
    await page.getByRole('checkbox', { name: /правилами/ }).check();
    await expect(page.getByRole('button', { name: 'Надіслати на модерацію' })).toBeDisabled();

    const seller = await api('seller');
    const cities = await (await seller.get('/api/v1/local/cities/?q=вінниц')).json();
    const resp = await seller.post('/api/v1/local/listings/', {
      data: {
        make: 'Skoda', model: '[E2E] Без відмітки', year: 2015, mileage_km: 1, price: '1000', currency: 'USD',
        fuel_type: 'petrol', transmission: 'manual', body_type: 'sedan', condition: 'used',
        region: cities[0].region, city: cities[0].id, description: '[E2E]', contact_phone: '+380501112293',
        agreed_to_rules: true,
      },
    });
    expect(resp.status()).toBe(400);
    expect(Object.keys(await resp.json())).toContain('legal_confirmed');
  });

  test('обхід: опис довший за ліміт з /local/config/ — лічильник червоний, кнопка неактивна', async ({ page, request }) => {
    const config = await (await request.get('/api/v1/local/config/')).json();
    expect(config.description_max).toBeGreaterThan(0);
    await page.goto('/local/new');
    await fillForm(page, 'я'.repeat(config.description_max + 1));
    await page.getByRole('checkbox', { name: /правилами/ }).check();
    await page.getByRole('checkbox', { name: /не в розшуку/ }).check();
    await expect(page.getByTestId('description-counter')).toHaveText(`${config.description_max + 1} / ${config.description_max}`);
    await expect(page.getByTestId('description-counter')).toHaveClass(/text-red-600/);
    await expect(page.getByRole('button', { name: 'Надіслати на модерацію' })).toBeDisabled();
  });

  test('ліміт: 429 від сервера — текст «Забагато нових оголошень»', async ({ page }) => {
    await page.route('**/api/v1/local/listings/', (route) => route.request().method() === 'POST'
      ? route.fulfill({
        status: 429, contentType: 'application/json',
        body: JSON.stringify({ detail: 'Забагато нових оголошень. Спробуйте пізніше' }),
      })
      : route.continue());
    await page.goto('/local/new');
    await fillForm(page);
    await page.getByRole('checkbox', { name: /правилами/ }).check();
    await page.getByRole('checkbox', { name: /не в розшуку/ }).check();
    await page.getByRole('button', { name: 'Надіслати на модерацію' }).click();
    await expect(page.getByText('Забагато нових оголошень. Спробуйте пізніше')).toBeVisible();
  });
});

test('правила містять пункти про розшук і заставу', async ({ page }) => {
  await page.addInitScript(consentInit);
  await page.goto('/rules');
  await expect(page.getByText('Оголошення про автомобіль, що перебуває в розшуку.')).toBeVisible();
  await expect(page.getByText(/у заставі або під арештом/)).toBeVisible();
});
