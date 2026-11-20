/**
 * E2E: open-redirect через ?next= на /login (задача 10.30, аудит F). Покупатель входит с вредным next —
 * попадает на /me, запросов к evil.example нет. Логика — lib/safe-next.ts.
 */
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

const GUEST = { cookies: [], origins: [] };

const EVIL_NEXT = [
  '//evil.example',
  '/%5Cevil.example',
  '/%09/evil.example',
  'javascript:alert(1)',
];

// Гідратація може скинути введене значення — повторюємо, доки обидва поля не тримають його.
async function fillLogin(page: Page, emailValue: string, passwordValue: string) {
  const email = page.locator('input[type="email"]');
  const pass = page.locator('input[type="password"]');
  await expect(async () => {
    await email.fill(emailValue);
    await pass.fill(passwordValue);
    await expect(email).toHaveValue(emailValue, { timeout: 500 });
    await expect(pass).toHaveValue(passwordValue, { timeout: 500 });
  }).toPass();
}

test.describe('safeNext на /login', () => {
  test.use({ storageState: GUEST });

  for (const next of EVIL_NEXT) {
    test(`next=${next} → /me, без запитів до evil.example`, async ({ page }) => {
      const password = process.env.E2E_PASSWORD;
      if (!password) throw new Error('E2E_PASSWORD не задано.');
      await page.goto(`/login?next=${next}`);
      await fillLogin(page, 'buyer@e2e.test', password);
      await expectNoRequest(
        page,
        (r) => r.url().includes('evil.example'),
        async () => {
          await page.getByRole('button', { name: 'Увійти' }).click();
          await expect(page).toHaveURL(/\/me$/);
        },
      );
      expect(new URL(page.url()).hostname).not.toContain('evil');
    });
  }
});
