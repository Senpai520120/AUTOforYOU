/**
 * E2E: защита входа от перебора (задача 1.5, 23-P9).
 * Стек e2e: LOGIN_MAX_FAILURES=5, LOGIN_LOCKOUT_MINUTES=1 (.env.e2e). Каждый тест — свой
 * email, чтобы блокировки не пересекались. Капча на входе — после задачи 1.6.
 */
import type { APIRequestContext } from '@playwright/test';
import { test, expect } from './fixtures';
import { captchaToken, captchaTokens, registerViaApi } from './helpers/captcha';

const GUEST = { cookies: [], origins: [] };
const MAX_FAILURES = 5;

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

async function register(request: APIRequestContext, email: string) {
  await registerViaApi(request, email, e2ePassword());
}

async function failLogins(request: APIRequestContext, email: string, n: number) {
  // После 3 неудач вход требует капчу (1.6): токен honeypot одноразовый — свой на каждый запрос.
  const tokens = await captchaTokens(request, n);
  for (let i = 0; i < n; i++) {
    const resp = await request.post('/api/v1/auth/token/', {
      data: { email, password: `${e2ePassword()}-wrong`, captcha_token: tokens[i] },
    });
    expect(resp.status()).toBe(401);
  }
}

test.describe('Блокування входу (23-P9)', () => {
  test.use({ storageState: GUEST });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('після блокування вірний пароль відхиляється з «Забагато спроб», потім вхід відновлюється', async ({
    page,
    request,
    uniqueEmail,
  }) => {
    test.setTimeout(150_000);
    await register(request, uniqueEmail);
    await failLogins(request, uniqueEmail, MAX_FAILURES);
    // Блокировка ставится на (MAX_FAILURES+1)-й попытке, а капча проверяется раньше неё (1.6):
    // эту попытку шлём с токеном, чтобы аккаунт реально оказался заблокирован.
    const lockToken = await captchaToken(request);
    const lockResp = await request.post('/api/v1/auth/token/', {
      data: { email: uniqueEmail, password: `${e2ePassword()}-wrong`, captcha_token: lockToken },
    });
    expect(lockResp.status()).toBe(429);

    await page.goto('/login');
    await page.locator('input[type="email"]').fill(uniqueEmail);
    await page.locator('input[type="password"]').fill(e2ePassword());
    const tokenResponse = page.waitForResponse(
      (r) => r.url().includes('/auth/token/') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Увійти' }).click();
    const resp = await tokenResponse;
    expect(resp.status()).toBe(429);
    expect(Number(resp.headers()['retry-after'])).toBeGreaterThan(0);

    await expect(page.getByText(/Забагато спроб/)).toBeVisible();
    await expect(page.getByText('Невірний email або пароль')).toBeHidden();
    await expect(page).toHaveURL(/\/login/);

    // Блокування тимчасове (LOGIN_LOCKOUT_MINUTES=1): запити під час блокування не продовжують її.
    await expect
      .poll(
        async () =>
          (
            await request.post('/api/v1/auth/token/', {
              data: { email: uniqueEmail, password: e2ePassword() },
            })
          ).status(),
        { timeout: 90_000, intervals: [5_000] },
      )
      .toBe(200);
  });

  test('N невірних паролів у формі → «Забагато спроб», а не «Невірний email або пароль»', async ({
    page,
    uniqueEmail,
  }) => {
    // Неіснуючий email поводиться так само, як існуючий (немає перебору адрес).
    await page.goto('/login');
    for (let i = 0; i < MAX_FAILURES; i++) {
      await page.locator('input[type="email"]').fill(uniqueEmail);
      await page.locator('input[type="password"]').fill(`wrong-${i}`);
      // Відповідь чекаємо явно: текст помилки попередньої спроби ще на екрані, і без цього
      // наступна спроба стартувала б, поки летить попередня (після 3-ї кнопка ще й чекає капчу).
      const attempt = page.waitForResponse(
        (r) => r.url().includes('/auth/token/') && r.request().method() === 'POST',
      );
      await page.getByRole('button', { name: 'Увійти' }).click();
      expect((await attempt).status()).toBe(401);
      await expect(page.getByText('Невірний email або пароль')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Увійти' })).toBeVisible();
    }
    await page.locator('input[type="password"]').fill('wrong-last');
    const tokenResponse = page.waitForResponse(
      (r) => r.url().includes('/auth/token/') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Увійти' }).click();
    // Саме блокування Django (retry_after в JSON), а не 429 від nginx limit_req.
    const resp = await tokenResponse;
    expect(resp.status()).toBe(429);
    expect((await resp.json()).retry_after).toBeGreaterThan(0);
    await expect(page.getByText(/Забагато спроб/)).toBeVisible();
  });
});
