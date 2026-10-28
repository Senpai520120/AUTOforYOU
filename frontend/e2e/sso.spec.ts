/**
 * E2E: вхід через SSO (Keycloak + Active Directory, задача SSO-1). @sso
 *
 * Потрібні: стек Users & Roles у режимі AD (Keycloak на localhost:8080), стек AUTOforYOU з
 * docker-compose.sso.yml і користувач ad_alice@corp.example.test (e2e_seed створює його при
 * OIDC_ENABLED; email обов'язково як в AD, тому не @e2e.test). Без E2E_SSO=1 сценарій пропускається.
 * Запуск: E2E_SSO=1 npx playwright test e2e/sso.spec.ts --project=chromium --no-deps
 */
import { test, expect } from './fixtures';

const GUEST = { cookies: [], origins: [] };
const AD_USER = 'ad_alice';
const AD_EMAIL = 'ad_alice@corp.example.test';
// Пароль тестових учёток AD стека Users & Roles (не секрет, лише для dev).
const AD_PASSWORD = 'demo-password-123';

test.describe('Вхід через SSO @sso', () => {
  test.skip(process.env.E2E_SSO !== '1', 'E2E_SSO не задано: потрібні Keycloak і docker-compose.sso.yml');
  test.use({ storageState: GUEST });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('/login → «Увійти через SSO» → Keycloak (ad_alice) → вхід у свій акаунт', async ({ page }) => {
    await page.goto('/login?next=%2Fme');
    await page.getByRole('link', { name: 'Увійти через SSO' }).click();

    await expect(page).toHaveURL(/localhost:8080\/realms\/myapp\//);
    await page.locator('#username').fill(AD_USER);
    await page.locator('#password').fill(AD_PASSWORD);
    await page.locator('#kc-login').click();

    await expect(page).toHaveURL(/localhost\/me$/);
    await expect(page.getByText(AD_EMAIL).first()).toBeVisible();
    const profile = await page.request.get('/api/v1/auth/profile/');
    expect(profile.status()).toBe(200);
    expect((await profile.json()).email).toBe(AD_EMAIL);
  });

  test('невірний пароль AD → лишаємося на Keycloak, сесії на сайті немає', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('link', { name: 'Увійти через SSO' }).click();
    await page.locator('#username').fill(AD_USER);
    await page.locator('#password').fill('wrong-password');
    await page.locator('#kc-login').click();

    await expect(page).toHaveURL(/localhost:8080\/realms\/myapp\//);
    const profile = await page.request.get('/api/v1/auth/profile/');
    expect(profile.status()).toBe(401);
  });
});
