import { expect, type APIRequestContext } from '@playwright/test';

// Сервер відхиляє форм-токен молодший за CAPTCHA_MIN_FILL_SECONDS=3.
const MIN_FILL_MS = 3200;

/**
 * `count` токенів капчі для прямих API-запитів e2e-стека. У стеку ключів Turnstile немає, тож діє
 * honeypot: токен форми з /auth/config/ ОДНОРАЗОВИЙ (один токен — один запит) і діє не раніше 3 с
 * після видачі. Усі токени запитуються разом, очікування одне.
 */
export async function captchaTokens(request: APIRequestContext, count: number): Promise<string[]> {
  const tokens: string[] = [];
  let honeypot = false;
  for (let i = 0; i < count; i++) {
    const resp = await request.get('/api/v1/auth/config/');
    expect(resp.status()).toBe(200);
    const { captcha } = (await resp.json()) as { captcha: { provider: string; form_token?: string } };
    honeypot = captcha.provider === 'honeypot';
    tokens.push(honeypot ? (captcha.form_token ?? '') : '');
  }
  // Єдине місце очікування: токен має «дозріти» на сервері, події для очікування немає.
  if (honeypot && count > 0) await new Promise((r) => setTimeout(r, MIN_FILL_MS));
  return tokens;
}

export async function captchaToken(request: APIRequestContext): Promise<string> {
  return (await captchaTokens(request, 1))[0];
}

/** Реєстрація через API (для тестів, яким потрібен новий неверифікований акаунт). */
export async function registerViaApi(request: APIRequestContext, email: string, password: string) {
  const resp = await request.post('/api/v1/auth/register/', {
    data: {
      email, password, password2: password,
      agreed_to_terms: true, confirmed_age_18: true,
      captcha_token: await captchaToken(request),
    },
  });
  expect(resp.status()).toBe(201);
}
