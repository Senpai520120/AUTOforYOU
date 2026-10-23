/**
 * E2E (API): JWT у httpOnly-cookie + CSRF (задача 1.3, 23-D20, частина 23-P8).
 * Бекенд через request API; браузерні сценарії фронту — auth-cookie.spec.ts (задача 1.4).
 */
import { test, expect } from './fixtures';

const GUEST = { cookies: [], origins: [] };

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

test.describe('Cookie-аутентифікація API', () => {
  test.use({ storageState: GUEST });

  test('вхід ставить httpOnly-cookie access і refresh', async ({ request }) => {
    const resp = await request.post('/api/v1/auth/token/', {
      data: { email: 'seller@e2e.test', password: e2ePassword() },
    });
    expect(resp.status()).toBe(200);

    const { cookies } = await request.storageState();
    const access = cookies.find((c) => c.name === 'access');
    const refresh = cookies.find((c) => c.name === 'refresh');
    expect(access?.httpOnly).toBe(true);
    expect(access?.sameSite).toBe('Lax');
    expect(refresh?.httpOnly).toBe(true);
    expect(refresh?.path).toBe('/api/v1/auth/');

    const profile = await request.get('/api/v1/auth/profile/');
    expect(profile.status()).toBe(200);
  });

  test('обхід: POST з cookie без X-CSRFToken → 403', async ({ request }) => {
    const login = await request.post('/api/v1/auth/token/', {
      data: { email: 'seller@e2e.test', password: e2ePassword() },
    });
    expect(login.status()).toBe(200);

    const resp = await request.post('/api/v1/auth/me/trusted-shops/', {
      data: { name: '[E2E] csrf-bypass' },
    });
    expect(resp.status()).toBe(403);
    expect(await resp.text()).toContain('CSRF');
  });
});
