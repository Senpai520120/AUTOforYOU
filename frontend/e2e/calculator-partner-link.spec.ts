/**
 * E2E: партнерське посилання carVertical у калькуляторі (задача 3.2a).
 * Адреса приходить з публічного /api/v1/site-settings/ (CARVERTICAL_PARTNER_URL у .env бекенда),
 * тому відповідь API підміняється в браузері: стек e2e тримає змінну порожньою, як прод до реєстрації в програмі.
 */
import { test, expect } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const SETTINGS = '**/api/v1/site-settings/';

test.describe('Калькулятор: партнерське посилання carVertical @smoke', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  test('є посилання з rel=sponsored і позначкою, коли URL заданий', async ({ page }) => {
    await page.route(SETTINGS, async (route) => {
      const resp = await route.fetch();
      const body = await resp.json();
      await route.fulfill({ response: resp, json: { ...body, carvertical_partner_url: 'https://partner.example/ref?id=e2e' } });
    });
    await page.goto('/calculator');
    const link = page.getByRole('link', { name: 'Перевірити авто за VIN (carVertical)' });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', 'https://partner.example/ref?id=e2e');
    await expect(link).toHaveAttribute('rel', /sponsored/);
    await expect(link).toHaveAttribute('rel', /noopener/);
    await expect(page.getByTestId('partner-vin-link')).toContainText('партнерське посилання');
  });

  test('порожній URL: блоку немає, сторінка без помилок', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.route(SETTINGS, async (route) => {
      const resp = await route.fetch();
      const body = await resp.json();
      await route.fulfill({ response: resp, json: { ...body, carvertical_partner_url: '' } });
    });
    const settingsLoaded = page.waitForResponse(SETTINGS);
    await page.goto('/calculator');
    await settingsLoaded;
    await expect(page.getByRole('heading', { name: /Калькулятор вартості/ })).toBeVisible();
    await expect(page.getByTestId('partner-vin-link')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('не https (javascript:) не виводиться', async ({ page }) => {
    await page.route(SETTINGS, async (route) => {
      const resp = await route.fetch();
      const body = await resp.json();
      await route.fulfill({ response: resp, json: { ...body, carvertical_partner_url: 'javascript:alert(1)' } });
    });
    const settingsLoaded = page.waitForResponse(SETTINGS);
    await page.goto('/calculator');
    await settingsLoaded;
    await expect(page.getByRole('heading', { name: /Калькулятор вартості/ })).toBeVisible();
    await expect(page.getByTestId('partner-vin-link')).toHaveCount(0);
  });
});
