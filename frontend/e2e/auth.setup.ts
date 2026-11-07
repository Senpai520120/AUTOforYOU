import { test as setup, expect } from '@playwright/test';
import path from 'path';

export const ROLES = ['buyer', 'seller', 'dealer', 'staff', 'broker', 'fakeadmin'] as const;
export type Role = (typeof ROLES)[number];
export const authFile = (role: Role) => path.join(__dirname, '.auth', `${role}.json`);

setup.setTimeout(240_000);

setup('стек готовий', async ({ request, baseURL }) => {
  const urls = ['/', '/api/v1/pricing/rates/'];
  const deadline = Date.now() + 180_000;
  let last = '';
  for (const url of urls) {
    for (;;) {
      try {
        const r = await request.get(url, { timeout: 10_000 });
        if (r.status() === 200) break;
        last = `${url} -> HTTP ${r.status()}`;
      } catch (e) {
        last = `${url} -> ${(e as Error).message.split('\n')[0]}`;
      }
      if (Date.now() > deadline) {
        throw new Error(
          `Стек ${baseURL} не став готовим за 180 с (${last}). ` +
            'Запустіть docker compose up -d і дочекайтесь healthy.',
        );
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
});

for (const role of ROLES) {
  setup(`вхід ${role}`, async ({ page }) => {
    const password = process.env.E2E_PASSWORD;
    if (!password) {
      throw new Error('E2E_PASSWORD не задано: експортуйте той самий пароль, з яким виконано e2e_seed.');
    }
    // page.request ділить cookie з контекстом браузера: httpOnly access/refresh з відповіді
    // потрапляють у storageState (задача 1.4 — токенів у тілі й у localStorage більше немає).
    const resp = await page.request.post('/api/v1/auth/token/', {
      data: { email: `${role}@e2e.test`, password },
    });
    if (resp.status() === 401 || resp.status() === 400) {
      throw new Error(
        `Вхід ${role}@e2e.test відхилено (HTTP ${resp.status()}): неправильний E2E_PASSWORD ` +
          'або не виконано `manage.py e2e_seed`.',
      );
    }
    expect(resp.ok(), `Вхід ${role}: HTTP ${resp.status()}`).toBeTruthy();
    const names = (await page.context().cookies()).map((c) => c.name);
    expect(names, `Вхід ${role}: немає cookie access/refresh`).toEqual(
      expect.arrayContaining(['access', 'refresh']),
    );
    await page.context().storageState({ path: authFile(role) });
  });
}
