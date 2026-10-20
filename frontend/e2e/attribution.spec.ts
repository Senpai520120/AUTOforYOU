/**
 * E2E: джерело візиту first-touch при реєстрації (задача 2.14, Н-37).
 * UTM живуть у sessionStorage (без cookie), уходять у тілі POST реєстрації; у власній
 * вивантаженні «Мої дані» користувач бачить своє джерело.
 */
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';

test.use({ storageState: { cookies: [], origins: [] } });

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

async function fillRegister(page: Page, email: string, password: string) {
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').first().fill(password);
  await page.locator('input[type="password"]').nth(1).fill(password);
  await page.getByLabel(/Погоджуюсь з/).check();
  await page.getByLabel(/18 років/).check();
}

async function submitRegister(page: Page) {
  const req = page.waitForRequest((r) => r.url().includes('/auth/register/') && r.method() === 'POST');
  await page.getByRole('button', { name: 'Зареєструватися' }).click();
  const request = await req;
  await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();
  return JSON.parse(request.postData() ?? '{}') as { attribution?: { utm?: Record<string, string> } };
}

async function myExport(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole('button', { name: 'Увійти' }).click();
  await expect(page).toHaveURL(/\/me$/);
  const resp = await page.request.get('/api/v1/auth/me/export/');
  expect(resp.status()).toBe(200);
  return (await resp.json()) as { profile: { first_touch_utm: Record<string, string> } };
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test('успіх: UTM з калькулятора доходить до реєстрації, лежить у sessionStorage, не в cookie', async ({
  page, uniqueEmail,
}) => {
  const password = e2ePassword();
  await page.goto('/calculator?utm_source=tiktok&utm_campaign=test');
  const stored = await page.evaluate(() => window.sessionStorage.getItem('afy:attribution'));
  expect(stored).toContain('tiktok');
  await page.goto('/register');
  await fillRegister(page, uniqueEmail, password);
  const body = await submitRegister(page);
  expect(body.attribution?.utm?.source).toBe('tiktok');
  const cookies = await page.context().cookies();
  expect(cookies.some((c) => c.value.includes('tiktok'))).toBe(false);
  const data = await myExport(page, uniqueEmail, password);
  expect(data.profile.first_touch_utm.source).toBe('tiktok');
});

test('обхід: сміття і довгий рядок у sessionStorage — реєстрація проходить, джерело порожнє', async ({
  page, uniqueEmail,
}) => {
  const password = e2ePassword();
  await page.goto('/register');
  await page.evaluate(() => window.sessionStorage.setItem('afy:attribution', JSON.stringify({
    utm: { source: 'x'.repeat(5000), evil: '<script>' }, referrer: 'javascript:alert(1)', entry_page_url: '//evil.test',
  })));
  await fillRegister(page, uniqueEmail, password);
  await submitRegister(page);
  const data = await myExport(page, uniqueEmail, password);
  expect(data.profile.first_touch_utm).toEqual({});
});

test('без UTM: attribution не надсилається, реєстрація працює', async ({ page, uniqueEmail }) => {
  const password = e2ePassword();
  await page.goto('/register');
  await page.evaluate(() => window.sessionStorage.removeItem('afy:attribution'));
  await fillRegister(page, uniqueEmail, password);
  const body = await submitRegister(page);
  expect(body.attribution).toBeUndefined();
});
