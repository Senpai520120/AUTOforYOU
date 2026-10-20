/**
 * E2E: фронт на cookie-аутентифікації (задача 1.4): 23-P8, 23-P3, 23-P4, 09-Q7/08-Q2, 08-S7, 11-S5.
 *
 * Кожен сценарій, що виходить або оновлює сесію, входить сам (не через storageState):
 * refresh ротується і відкликається, спільний стан ролей зламався б для інших тестів.
 */
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

const GUEST = { cookies: [], origins: [] };
const REFRESH_PATH = '/api/v1/auth/token/refresh/';

function e2ePassword(): string {
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error('E2E_PASSWORD не задано.');
  return password;
}

async function apiLogin(page: Page, email = 'seller@e2e.test') {
  const resp = await page.request.post('/api/v1/auth/token/', { data: { email, password: e2ePassword() } });
  expect(resp.status()).toBe(200);
}

async function cookie(page: Page, name: string) {
  return (await page.context().cookies()).find((c) => c.name === name);
}

const logoutButton = (page: Page) => page.getByRole('banner').getByRole('button', { name: 'Вийти' });

test.use({ storageState: GUEST });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('23-P8: вхід через форму', () => {
  test('сесія тільки в httpOnly-cookie, SSR працює після входу', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('seller@e2e.test');
    await page.locator('input[type="password"]').fill(e2ePassword());
    await page.getByRole('button', { name: 'Увійти' }).click();
    await expect(page).toHaveURL(/\/me$/);
    await expect(logoutButton(page)).toBeVisible();

    const keys = await page.evaluate(() => Object.keys(localStorage));
    expect(keys).not.toContain('access');
    expect(keys).not.toContain('refresh');
    const access = await cookie(page, 'access');
    expect(access?.httpOnly).toBe(true);
    expect(access?.sameSite).toBe('Lax');
    expect((await cookie(page, 'refresh'))?.httpOnly).toBe(true);

    // Авторизований SSR (serverGetAuthed): сервер Next бачить сесію з cookie access.
    const html = await (await page.request.get('/me')).text();
    expect(html).toContain('data-ssr-auth="user"');

    // Публічна SSR-сторінка після входу рендериться як і раніше.
    const listings = await page.goto('/listings');
    expect(listings?.status()).toBe(200);
    await expect(logoutButton(page)).toBeVisible();
  });

  test('обхід: SSR одного користувача не дістається гостю (немає кешу)', async ({ page, playwright, baseURL }) => {
    await apiLogin(page);
    expect(await (await page.request.get('/me')).text()).toContain('data-ssr-auth="user"');

    const guest = await playwright.request.newContext({ baseURL, storageState: GUEST });
    try {
      const html = await (await guest.get('/me')).text();
      expect(html).toContain('data-ssr-auth="guest"');
      expect(html).not.toContain('seller@e2e.test');
    } finally {
      await guest.dispose();
    }
  });

  test('старі токени з localStorage (до 1.4) прибираються при завантаженні', async ({ page }) => {
    await page.addInitScript(() => {
      if (!sessionStorage.getItem('seeded')) {
        localStorage.setItem('access', 'legacy-access');
        localStorage.setItem('refresh', 'legacy-refresh');
        sessionStorage.setItem('seeded', '1');
      }
    });
    await page.goto('/');
    await expect.poll(() => page.evaluate(() => localStorage.getItem('refresh'))).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem('access'))).toBeNull();
  });

  test('гість без мітки сесії не шле profile і refresh', async ({ page }) => {
    await expectNoRequest(
      page,
      (r) => /\/auth\/(profile|token\/refresh)\//.test(r.url()),
      async () => {
        await page.goto('/listings');
        await expect(page.getByRole('banner').getByRole('link', { name: 'Увійти' })).toBeVisible();
      },
    );
  });

  test('обхід: POST з cookie, але без X-CSRFToken → 403', async ({ page }) => {
    await apiLogin(page);
    const resp = await page.request.post('/api/v1/auth/me/trusted-shops/', {
      data: { name: '[E2E] csrf-bypass' },
    });
    expect(resp.status()).toBe(403);
    expect(await resp.text()).toContain('CSRF');
  });
});

test.describe('23-P3: вихід відкликає refresh', () => {
  test('після «Вийти» /me → /login?next=%2Fme, старий refresh → 401', async ({ page, playwright, baseURL }) => {
    await apiLogin(page);
    await page.goto('/me');
    await expect(logoutButton(page)).toBeVisible();
    const oldRefresh = await cookie(page, 'refresh');
    expect(oldRefresh).toBeTruthy();

    const logout = page.waitForResponse((r) => r.url().includes('/auth/token/logout/'));
    await logoutButton(page).click();
    expect((await logout).status()).toBe(200);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('banner').getByRole('link', { name: 'Увійти' })).toBeVisible();
    expect(await cookie(page, 'access')).toBeUndefined();
    expect(await cookie(page, 'refresh')).toBeUndefined();

    await page.goto('/me');
    await expect(page).toHaveURL(/\/login\?next=%2Fme$/);

    // Окремий контекст лише зі старою cookie: тіло порожнє, refresh з cookie, CSRF є.
    const ctx = await playwright.request.newContext({ baseURL, storageState: { cookies: [oldRefresh!], origins: [] } });
    try {
      await ctx.get('/api/v1/auth/csrf/');
      const csrf = (await ctx.storageState()).cookies.find((c) => c.name === 'csrftoken')?.value ?? '';
      const resp = await ctx.post(REFRESH_PATH, { headers: { 'X-CSRFToken': csrf } });
      expect(resp.status()).toBe(401);
    } finally {
      await ctx.dispose();
    }
  });
});

test.describe('08-S2: невдалий вихід не вдає вихід', () => {
  test('обхід: мережа впала на logout → повідомлення, сесія не «зникла» лише на клієнті', async ({ page }) => {
    await apiLogin(page);
    await page.goto('/me');
    await expect(logoutButton(page)).toBeVisible();
    await page.route('**/api/v1/auth/token/logout/', (route) => route.abort());

    // alert() блокує сторінку до закриття діалогу: приймаємо його в самому обробнику події
    // (а не після await у тесті), щоб не залежати від гонки між click() і accept() у повільному CI.
    const messages: string[] = [];
    page.on('dialog', (d) => { messages.push(d.message()); void d.accept().catch(() => {}); });
    await logoutButton(page).click({ noWaitAfter: true });
    await expect.poll(() => messages.length, { timeout: 15_000 }).toBeGreaterThan(0);
    expect(messages[0]).toContain('Не вдалося вийти');

    await expect(page).toHaveURL(/\/me$/);
    await expect(logoutButton(page)).toBeVisible();
    expect(await cookie(page, 'refresh')).toBeTruthy();
  });
});

test.describe('23-P4: протухлий access і паралельні запити', () => {
  test('кілька 401 одночасно → рівно один refresh, користувач лишається в сесії', async ({ page }) => {
    const counters = (status: number) => Promise.all(
      ['/messages/unread-count/', '/notifications/unread-count/'].map((path) =>
        page.waitForResponse((r) => r.url().includes(path) && r.status() === status)),
    );
    await page.clock.install();
    await apiLogin(page);
    // Перше завантаження лічильників (200) — дочекатися, щоб не сплутати з повтором після refresh.
    const initial = counters(200);
    await page.goto('/me');
    await expect(logoutButton(page)).toBeVisible();
    await initial;

    // Браузер видаляє cookie access після Max-Age — сервер бачить те саме, що через 15 хвилин.
    await page.context().clearCookies({ name: 'access' });
    const refreshes: string[] = [];
    page.on('request', (r) => { if (r.url().includes(REFRESH_PATH)) refreshes.push(r.url()); });

    const rejected = counters(401);
    const refreshed = page.waitForResponse((r) => r.url().includes(REFRESH_PATH));
    const retried = counters(200);
    // Шапка опитує два лічильники паралельно раз на 30 с.
    await page.clock.fastForward(30_000);
    await rejected;
    expect((await refreshed).status()).toBe(200);
    await retried;

    expect(refreshes).toHaveLength(1);
    expect(await cookie(page, 'access')).toBeTruthy();
    await expect(logoutButton(page)).toBeVisible();
    await expect(page).toHaveURL(/\/me$/);
  });

  test('обхід: refresh теж зник → зрозумілий перехід на /login', async ({ page }) => {
    await page.clock.install();
    await apiLogin(page);
    await page.goto('/me');
    await expect(logoutButton(page)).toBeVisible();

    await page.context().clearCookies({ name: 'access' });
    await page.context().clearCookies({ name: 'refresh' });
    await page.clock.fastForward(30_000);

    await expect(page).toHaveURL(/\/login\?next=%2Fme$/);
    await expect(page.getByRole('heading', { name: 'Вхід' })).toBeVisible();
  });
});

test.describe('09-Q7 / 08-Q2: протухла cookie не заважає гостю', () => {
  test('гість зі сміттєвою cookie access рахує на калькуляторі без редіректу', async ({ page, baseURL }) => {
    await page.context().addCookies([{ name: 'access', value: 'garbage.token.value', url: baseURL! }]);
    await page.goto('/calculator');

    await page.getByLabel('Ціна аукціону ($)', { exact: true }).fill('5000');
    await page.getByLabel("Об'єм двигуна (см³)", { exact: true }).fill('2000');
    await page.getByLabel('Рік випуску', { exact: true }).fill('2018');
    await page.getByRole('button', { name: 'Розрахувати' }).click();

    await expect(page.getByRole('heading', { name: 'Деталізація вартості «під ключ»' })).toBeVisible();
    await expect(page).toHaveURL(/\/calculator$/);
  });
});

test.describe('08-S7: повернення за ?next=', () => {
  test('гість на /me/favorites → вхід → назад на /me/favorites', async ({ page }) => {
    await page.goto('/me/favorites');
    await expect(page).toHaveURL(/\/login\?next=%2Fme%2Ffavorites$/);
    await page.waitForLoadState('networkidle');
    await page.locator('input[type="email"]').fill('buyer@e2e.test');
    await page.locator('input[type="password"]').fill(e2ePassword());
    await page.getByRole('button', { name: 'Увійти' }).click();
    await expect(page).toHaveURL(/\/me\/favorites$/);
  });

  for (const evil of [
    'https://evil.example',
    '//evil.example',
    '/\\evil.example',
    '/\t/evil.example',
    '/\n/evil.example',
    'javascript:alert(1)',
  ]) {
    // Назва без керуючих символів (таб, перенос) — інакше її не знайти через --grep.
    const label = JSON.stringify(evil);
    test(`обхід: next=${label} ігнорується`, async ({ page, baseURL }) => {
      await page.goto(`/login?next=${encodeURIComponent(evil)}`);
      await page.waitForLoadState('networkidle'); // форма має гідратуватися до кліку
      await page.locator('input[type="email"]').fill('buyer@e2e.test');
      await page.locator('input[type="password"]').fill(e2ePassword());
      await page.getByRole('button', { name: 'Увійти' }).click();
      await expect(page).toHaveURL(/\/me$/);
      expect(new URL(page.url()).origin).toBe(new URL(baseURL!).origin);
    });
  }
});

test.describe('11-S5: сторінка /cookies', () => {
  test('описує httpOnly-cookie, а не токени в localStorage', async ({ page }) => {
    await page.goto('/cookies');
    const main = page.locator('main');
    await expect(main).toContainText('HttpOnly');
    await expect(main.getByRole('row', { name: /access/ })).toContainText('cookie, HttpOnly');
    await expect(main.getByRole('row', { name: /^refresh/ })).toContainText('cookie, HttpOnly');
    await expect(main.getByRole('row', { name: /csrftoken/ }).first()).toBeVisible();
    await expect(main.getByRole('row', { name: /access/ })).not.toContainText('localStorage');
  });
});
