/**
 * E2E: единые состояния загрузка / пусто / ошибка, откат мутаций, ConfirmDialog, серверный
 * редирект гостя (задача 6.2; 23-P5, 23-P39, 23-P45, 23-P46, 08-S7).
 * Ошибки API моделируются через page.route (500 / abort). Страницы C2C-социалки пропускаются,
 * если раздел выключен (флаги из /api/v1/site-settings/, как в c2c-flag.spec.ts).
 */
import type { Page, Route } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

type Flags = { c2c_enabled: boolean; c2c_public_posting_enabled: boolean; payments_enabled: boolean };
let flags: Flags;

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  const res = await ctx.get('/api/v1/site-settings/');
  expect(res.status()).toBe(200);
  flags = await res.json();
  await ctx.dispose();
});

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const GUEST = { cookies: [], origins: [] };
const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
const fail500 = (route: Route) => json(route, { detail: 'Traceback: secret server text' }, 500);

const UNAVAILABLE = 'Сервіс тимчасово недоступний';
const OFFLINE = "Немає з'єднання з сервером";
const RETRY = 'Спробувати ще раз';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(consentInit);
});

test.describe('23-P45: оформлена 404', () => {
  test('неіснуюча сторінка → 404 з посиланням на головну', async ({ page }) => {
    const resp = await page.goto('/neisnuyucha-storinka');
    expect(resp?.status()).toBe(404);
    await expect(page.getByRole('main').getByRole('link', { name: /головн/i }).first()).toHaveAttribute('href', '/');
  });
});

test.describe('Помилка завантаження ≠ порожній стан (23-P5, 23-P45)', () => {
  test.use({ storageState: storageStatePath('buyer') });

  const PAGES: { path: string; api: string; empty: string; c2c: boolean }[] = [
    { path: '/me/favorites', api: '**/api/v1/favorites/**', empty: 'Тут будуть збережені оголошення.', c2c: false },
    { path: '/me/calculations', api: '**/api/v1/auth/me/calculations/**', empty: 'Розрахунків поки немає', c2c: false },
    { path: '/me/deals', api: '**/api/v1/deals/**', empty: 'Угод поки немає.', c2c: true },
    { path: '/me/local-listings', api: '**/api/v1/local/my-listings/**', empty: 'Оголошень ще немає', c2c: true },
    { path: '/me/saved-searches', api: '**/api/v1/saved-searches/**', empty: 'Немає збережених пошуків.', c2c: true },
    { path: '/me/messages', api: '**/api/v1/messages/conversations/**', empty: 'Немає діалогів.', c2c: true },
  ];

  for (const p of PAGES) {
    test(`${p.path}: 500 → ErrorState, повтор завантажує дані`, async ({ page }) => {
      test.skip(p.c2c && !(flags.c2c_enabled && flags.c2c_public_posting_enabled), 'C2C-соціалка вимкнена');
      let broken = true;
      await page.route(p.api, route => (broken ? fail500(route) : route.fallback()));
      await page.goto(p.path);
      await expect(page.getByText(UNAVAILABLE)).toBeVisible();
      await expect(page.getByText(p.empty)).toHaveCount(0);
      await expect(page.getByText('secret server text')).toHaveCount(0);
      broken = false;
      await page.getByRole('button', { name: RETRY }).click();
      await expect(page.getByText(UNAVAILABLE)).toHaveCount(0);
      await expect(page.getByRole('button', { name: RETRY })).toHaveCount(0);
    });

    test(`${p.path}: обрив мережі → «${OFFLINE}»`, async ({ page }) => {
      test.skip(p.c2c && !(flags.c2c_enabled && flags.c2c_public_posting_enabled), 'C2C-соціалка вимкнена');
      await page.route(p.api, route => route.abort());
      await page.goto(p.path);
      await expect(page.getByText(OFFLINE)).toBeVisible();
      await expect(page.getByText(p.empty)).toHaveCount(0);
    });
  }
});

test.describe('Порожні стани (23-P46)', () => {
  test.use({ storageState: storageStatePath('buyer') });

  const EMPTY: { path: string; api: string; body: unknown; text: string; c2c: boolean }[] = [
    { path: '/me/favorites', api: '**/api/v1/favorites/', body: [], text: 'Тут будуть збережені оголошення.', c2c: false },
    { path: '/me/messages', api: '**/api/v1/messages/conversations/', body: [], text: 'Немає діалогів.', c2c: true },
    { path: '/me/local-listings', api: '**/api/v1/local/my-listings/', body: { count: 0, results: [] }, text: 'Оголошень ще немає', c2c: true },
    { path: '/me/saved-searches', api: '**/api/v1/saved-searches/', body: [], text: 'Немає збережених пошуків.', c2c: true },
  ];

  for (const e of EMPTY) {
    test(`${e.path}: порожній список → EmptyState`, async ({ page }) => {
      test.skip(e.c2c && !(flags.c2c_enabled && flags.c2c_public_posting_enabled), 'C2C-соціалка вимкнена');
      await page.route(e.api, route => json(route, e.body));
      await page.goto(e.path);
      await expect(page.getByText(e.text)).toBeVisible();
      await expect(page.getByRole('button', { name: RETRY })).toHaveCount(0);
    });
  }
});

test.describe('Відкат мутацій при помилці (23-P39, 08-Q7)', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('сповіщення: «Прочитати все» → 500: лічильник не обнулився, є повідомлення', async ({ page }) => {
    const item = (id: number) => ({
      id, type: 'new_message', title: `[E2E] Сповіщення ${id}`, text: '', link: '', is_read: false,
      created_at: new Date().toISOString(),
    });
    await page.route('**/api/v1/notifications/', route => json(route, [item(1), item(2)]));
    await page.route('**/api/v1/notifications/mark-read/', fail500);
    await page.goto('/me/notifications');
    await expect(page.getByText('[E2E] Сповіщення 1')).toBeVisible();
    await page.getByRole('button', { name: 'Позначити всі прочитаними' }).click();
    await expect(page.getByRole('alert').filter({ hasText: UNAVAILABLE })).toBeVisible();
    // Кнопка «прочитати все» на місці: непрочитані не зникли.
    await expect(page.getByRole('button', { name: 'Позначити всі прочитаними' })).toBeVisible();
  });

  test('збережені пошуки: DELETE → 500: запис лишається, є повідомлення; скасування не видаляє', async ({ page }) => {
    test.skip(!(flags.c2c_enabled && flags.c2c_public_posting_enabled), 'C2C-соціалка вимкнена');
    const search = { id: 9001, name: '[E2E] Пошук', filters: { make: 'Audi' }, notify: true, last_notified_at: null, created_at: new Date().toISOString() };
    let deletes = 0;
    page.on('dialog', () => { throw new Error('нативний dialog не очікується'); });
    await page.route('**/api/v1/saved-searches/', route => json(route, [search]));
    await page.route('**/api/v1/saved-searches/9001/', route => {
      if (route.request().method() === 'DELETE') { deletes += 1; return fail500(route); }
      return route.fallback();
    });
    await page.goto('/me/saved-searches');
    await page.getByRole('button', { name: 'Видалити' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Скасувати' }).click();
    await expect(dialog).toHaveCount(0);
    expect(deletes).toBe(0);
    await page.getByRole('button', { name: 'Видалити' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Видалити' }).click();
    await expect(page.getByRole('alert').filter({ hasText: UNAVAILABLE })).toBeVisible();
    await expect(page.getByText('[E2E] Пошук')).toBeVisible();
  });
});

test.describe('Партнери: ConfirmDialog замість confirm()', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('«Скасувати» — запис на місці, «Видалити» — зникає, нативних діалогів немає', async ({ page }) => {
    let shops = [{ id: 7001, name: '[E2E] СТО', type: 'service', contacts: '', rating: 5, notes: '' }];
    let nativeDialogs = 0;
    page.on('dialog', d => { nativeDialogs += 1; void d.dismiss(); });
    await page.route('**/api/v1/auth/me/trusted-shops/', route => json(route, { count: shops.length, results: shops }));
    await page.route('**/api/v1/auth/me/trusted-shops/7001/', route => {
      if (route.request().method() === 'DELETE') { shops = []; return route.fulfill({ status: 204 }); }
      return route.fallback();
    });
    await page.goto('/me/trusted-shops');
    await expect(page.getByText('[E2E] СТО')).toBeVisible();

    await page.getByRole('button', { name: 'Видалити' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Скасувати' }).click();
    await expect(page.getByText('[E2E] СТО')).toBeVisible();

    await page.getByRole('button', { name: 'Видалити' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Видалити' }).click();
    await expect(page.getByText('[E2E] СТО')).toHaveCount(0);
    await expect(page.getByText('Партнерів поки немає')).toBeVisible();
    expect(nativeDialogs).toBe(0);
  });

  test('створення партнера → 500: форма не зависає, видно повідомлення', async ({ page }) => {
    await page.route('**/api/v1/auth/me/trusted-shops/', route => {
      if (route.request().method() === 'POST') return fail500(route);
      return json(route, { count: 0, results: [] });
    });
    await page.goto('/me/trusted-shops');
    await page.getByRole('button', { name: '+ Додати' }).click();
    await page.getByPlaceholder('Назва').fill('[E2E] Новий');
    await page.getByRole('button', { name: 'Зберегти' }).click();
    await expect(page.getByRole('alert').filter({ hasText: UNAVAILABLE })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Зберегти' })).toBeEnabled();
  });
});

test.describe('C2C: регіони, редагування, тарифи (10-Q7)', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test.beforeEach(() => {
    test.skip(!(flags.c2c_enabled && flags.c2c_public_posting_enabled), 'подача оголошень вимкнена');
  });

  test('/local/new: regions → 500 → ErrorState замість порожнього select', async ({ page }) => {
    await page.route('**/api/v1/local/regions/', fail500);
    await page.goto('/local/new');
    await expect(page.getByText(UNAVAILABLE)).toBeVisible();
    await expect(page.getByRole('button', { name: RETRY })).toBeVisible();
    await expect(page.locator('select')).toHaveCount(0);
  });

  test('/local/<чужий id>/edit → 404: «Оголошення не знайдено», URL не змінився', async ({ page }) => {
    await page.route('**/api/v1/local/listings/999999/', route => json(route, { detail: 'Not found.' }, 404));
    await page.goto('/local/999999/edit');
    await expect(page.getByText('Оголошення не знайдено')).toBeVisible();
    await expect(page).toHaveURL(/\/local\/999999\/edit$/);
  });

  test('/local/<id>/edit → 403: «Немає доступу»', async ({ page }) => {
    await page.route('**/api/v1/local/listings/999998/', route => json(route, { detail: 'Forbidden' }, 403));
    await page.goto('/local/999998/edit');
    await expect(page.getByText('Немає доступу').first()).toBeVisible();
  });

  test('PromoteModal: порожній список тарифів → «Просування тимчасово недоступне»', async ({ page }) => {
    test.skip(!flags.payments_enabled, 'платежі вимкнені: модалка не виводиться');
    await page.route('**/api/v1/local/tariffs/', route => json(route, []));
    await page.goto('/me/local-listings');
    const promote = page.getByRole('button', { name: /Підняти|ТОП/ }).first();
    test.skip((await promote.count()) === 0, 'немає активного оголошення для просування');
    await promote.click();
    await expect(page.getByText('Просування тимчасово недоступне')).toBeVisible();
  });
});

test.describe('PAYMENTS_ENABLED: кнопки просування', () => {
  test.use({ storageState: storageStatePath('buyer') });

  // Прапорці приходять з SSR (app/layout.tsx -> C2CProvider), підмінити їх у браузері не можна:
  // кожен тест перевіряє фактичний стан стеку, протилежний варіант пропускається.
  async function openMyListings(page: Page) {
    const listing = {
      id: 8001, make: 'Audi', model: 'A4', year: 2018, price: '10000', currency: 'USD', mileage_km: 100000,
      city_name: 'Київ', region_name: 'Київська', status: 'active', expires_at: null, promoted_until: null,
      rejection_reason: '', created_at: new Date().toISOString(),
    };
    await page.route('**/api/v1/local/my-listings/', route => json(route, { count: 1, results: [listing] }));
    await page.goto('/me/local-listings');
  }

  test('payments_enabled=false → кнопок «Підняти»/«ТОП» немає', async ({ page }) => {
    test.skip(!(flags.c2c_enabled && flags.c2c_public_posting_enabled), 'C2C-соціалка вимкнена');
    test.skip(flags.payments_enabled, 'стек з PAYMENTS_ENABLED=true');
    await openMyListings(page);
    await expect(page.getByText('Audi A4 2018')).toBeVisible();
    await expect(page.getByRole('button', { name: /Підняти/ })).toHaveCount(0);
  });

  test('payments_enabled=true → кнопка «Підняти» є', async ({ page }) => {
    test.skip(!(flags.c2c_enabled && flags.c2c_public_posting_enabled), 'C2C-соціалка вимкнена');
    test.skip(!flags.payments_enabled, 'стек з PAYMENTS_ENABLED=false');
    await openMyListings(page);
    await expect(page.getByRole('button', { name: /Підняти/ })).toBeVisible();
  });
});

test.describe('R3.1: loading.tsx публічних маршрутів', () => {
  test.use({ storageState: GUEST });

  // Link пребфетчить /calculator у viewport, тож loading.tsx на навігації не відображається: стан недетермінований.
  test.fixme('R3.1 → 6.2: перехід на /calculator з головної показує role=status, потім контент (prefetch прибирає loading-стан)', async ({ page }) => {
    await page.goto('/');
    await page.route(url => url.pathname === '/calculator' && url.searchParams.has('_rsc'), async route => {
      await new Promise(r => setTimeout(r, 1500));
      await route.continue();
    });
    await page.locator('a[href="/calculator"]').first().click();
    await expect(page.getByRole('status').first()).toBeVisible();
    await expect(page).toHaveURL(/\/calculator$/);
  });
});

test.describe('08-S7: серверний редірект гостя (proxy.ts)', () => {
  test.use({ storageState: GUEST });

  const PROXY_PATHS = ['/me', '/me/favorites', '/me/local-listings', '/me/messages', '/local/new', '/local/1/edit'];

  for (const path of PROXY_PATHS) {
    test(`${path} без cookie → 307 на /login?next=`, async ({ request }) => {
      const resp = await request.get(path, { maxRedirects: 0 });
      expect(resp.status()).toBe(307);
      expect(resp.headers()['location']).toBe(`/login?next=${encodeURIComponent(path)}`);
    });
  }

  test('query зберігається в next', async ({ request }) => {
    const resp = await request.get('/me/favorites?x=1', { maxRedirects: 0 });
    expect(resp.status()).toBe(307);
    expect(resp.headers()['location']).toBe('/login?next=%2Fme%2Ffavorites%3Fx%3D1');
  });

  for (const path of ['/', '/ua', '/calculator']) {
    test(`публічний ${path} без cookie → 200`, async ({ request }) => {
      const resp = await request.get(path, { maxRedirects: 0 });
      expect(resp.status()).toBe(200);
    });
  }

  test('лише has_session=1 без токенів: редіректу немає, але API → 401 і клієнт веде на /login', async ({ page, context, baseURL }) => {
    await context.addCookies([{ name: 'has_session', value: '1', url: baseURL! }]);
    const resp = await page.request.get('/me', { maxRedirects: 0 });
    expect(resp.status()).toBe(200);
    await page.goto('/me/favorites');
    await expect(page).toHaveURL(/\/login\?next=%2Fme%2Ffavorites/);
  });
});

test.describe('08-S7: авторизований buyer', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('/me → 200 без редіректу', async ({ request }) => {
    const resp = await request.get('/me', { maxRedirects: 0 });
    expect(resp.status()).toBe(200);
  });
});
