/**
 * E2E: флаги раздела «Оголошення по Україні» (задача 6.7).
 *
 * Стек Playwright поднимается с одним набором env, а серверные запросы Next нельзя подменить через
 * page.route. Поэтому режим читается из GET /api/v1/site-settings/, а блоки чужих режимов пропускаются
 * через test.skip с причиной. Стек по умолчанию - ВОЛНА-2 (.env.e2e.example: оба флага и платежи on),
 * чтобы работали спеки подачи, переписки, сделок и избранного. Режимы off и засев в этом файле
 * прогоняются на отдельном стеке (см. .env.e2e.example); бэкенд-сторону обоих режимов покрывают
 * Django-тесты (core/tests_c2c_flag.py, local_listings/tests_posting.py).
 */
import { test, expect, storageStatePath } from './fixtures';
import { expectNoRequest } from './helpers/network';

type Mode = 'off' | 'seeding' | 'full';
type Flags = { c2c_enabled: boolean; c2c_public_posting_enabled: boolean; payments_enabled: boolean };

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const SOON = 'Оголошення по Україні — незабаром';
const POSTING_SOON = 'Подача оголошень скоро відкриється';
const GUEST = { cookies: [], origins: [] };

let flags: Flags;
let mode: Mode;
let listingId: number | null = null;

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  const res = await ctx.get('/api/v1/site-settings/');
  expect(res.status()).toBe(200);
  flags = await res.json();
  mode = !flags.c2c_enabled ? 'off' : flags.c2c_public_posting_enabled ? 'full' : 'seeding';
  if (flags.c2c_enabled) {
    const list = await ctx.get('/api/v1/local/listings/');
    expect(list.status()).toBe(200);
    const body = await list.json();
    listingId = body.results?.[0]?.id ?? null;
  }
  await ctx.dispose();
});

test.beforeEach(async ({ page }) => {
  await page.addInitScript(consentInit);
});

test.describe('site-settings: флаги C2C', () => {
  test('ответ содержит три булевых флага @smoke', async ({ request }) => {
    const body = await (await request.get('/api/v1/site-settings/')).json();
    for (const key of ['c2c_enabled', 'c2c_public_posting_enabled', 'payments_enabled']) {
      expect(typeof body[key], key).toBe('boolean');
    }
  });

  test('callback LiqPay флагами не закрыт (не 404)', async ({ request }) => {
    const res = await request.post('/api/v1/payments/liqpay/callback/', { data: { data: 'x', signature: 'bad' } });
    expect(res.status()).not.toBe(404);
  });
});

test.describe('Раздел выключен (C2C off)', () => {
  test.beforeEach(() => {
    test.skip(mode !== 'off', `стек в режиме "${mode}", блок только для C2C_ENABLED=false`);
  });
  test.use({ storageState: GUEST });

  test('шапка и главная без пунктов C2C @smoke', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'Порахувати вартість' })).toBeVisible();
    await expect(page.getByRole('banner').locator('a[href="/ua"]')).toHaveCount(0);
    await expect(page.locator('main a[href="/ua"]')).toHaveCount(0);
    await expect(page.getByTestId('home-ua-soon')).toBeVisible();
  });

  for (const path of ['/ua', '/local/1', '/local/new', '/local/1/edit', '/me/deals', '/me/local-listings', '/me/saved-searches', '/me/messages']) {
    test(`${path} → «Скоро» с noindex и ссылкой на калькулятор`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole('heading', { name: SOON })).toBeVisible();
      await expect(page.getByRole('link', { name: 'Перейти до калькулятора' })).toHaveAttribute('href', '/calculator');
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow');
    });
  }

  test('sitemap без /ua и /local/, robots закрывает /ua', async ({ request }) => {
    const sitemap = await (await request.get('/sitemap.xml')).text();
    expect(sitemap).not.toContain('/ua');
    expect(sitemap).not.toContain('/local/');
    const robots = await (await request.get('/robots.txt')).text();
    expect(robots).toContain('Disallow: /ua');
    expect(robots).toContain('Disallow: /local/');
  });

  test('API закрыт: local, messages, payments → 404', async ({ request }) => {
    expect((await request.get('/api/v1/local/listings/')).status()).toBe(404);
    expect((await request.get('/api/v1/messages/conversations/')).status()).toBe(404);
    expect((await request.post('/api/v1/payments/liqpay/checkout/', { data: {} })).status()).toBe(404);
  });

  test('калькулятор работает', async ({ page }) => {
    const resp = await page.goto('/calculator');
    expect(resp?.status()).toBe(200);
  });

  test.describe('375 px', () => {
    test.use({ viewport: { width: 375, height: 800 } });
    test('страница «Скоро» без горизонтального скролла @mobile', async ({ page }) => {
      await page.goto('/ua');
      await expect(page.getByRole('heading', { name: SOON })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  });
});

test.describe('Засев (C2C on, подача закрыта)', () => {
  test.beforeEach(() => {
    test.skip(mode !== 'seeding', `стек в режиме "${mode}", блок только для C2C_ENABLED=true + C2C_PUBLIC_POSTING_ENABLED=false`);
  });

  test.describe('гость', () => {
    test.use({ storageState: GUEST });

    test('/ua: каталог виден, кнопок «Подати оголошення» и «Зберегти пошук» нет @smoke', async ({ page }) => {
      await page.goto('/ua?make=Skoda');
      await expect(page.getByRole('heading', { name: 'Каталог Україна' })).toBeVisible();
      await expect(page.getByRole('link', { name: /Подати оголошення/ })).toHaveCount(0);
      await expect(page.getByRole('button', { name: /Зберегти пошук/ })).toHaveCount(0);
      await expect(page.getByRole('banner').locator('a[href="/ua"]')).toBeVisible();
    });

    test('карточка: гость видит приглашение войти, кнопок связи нет', async ({ page }) => {
      test.skip(listingId === null, 'в каталоге нет объявлений (запустите e2e_seed)');
      await page.goto(`/local/${listingId}`);
      await expect(page.getByRole('link', { name: 'Увійдіть, щоб побачити телефон' })).toHaveAttribute('href', '/login');
      for (const name of [/Написати/, /Запропонувати угоду/, /Поскаржитися/]) {
        await expect(page.getByRole('button', { name })).toHaveCount(0);
        await expect(page.getByRole('link', { name })).toHaveCount(0);
      }
    });

    test('/local/new → редирект на вход', async ({ page }) => {
      await page.goto('/local/new');
      await expect(page).toHaveURL(/\/login/);
    });

    test('sitemap содержит /ua', async ({ request }) => {
      expect(await (await request.get('/sitemap.xml')).text()).toContain('/ua');
    });

    test('нечисловая цена → понятная ошибка, а не падение', async ({ page }) => {
      const resp = await page.goto('/ua?price_min=abc');
      expect(resp?.status()).toBe(200);
      await expect(page.getByTestId('ua-filter-error')).toContainText('Некоректне значення');
    });
  });

  test.describe('buyer', () => {
    test.use({ storageState: storageStatePath('buyer') });

    test('/local/new → «Подача оголошень скоро відкриється» со ссылкой в каталог', async ({ page }) => {
      await page.goto('/local/new');
      await expect(page.getByRole('heading', { name: POSTING_SOON })).toBeVisible();
      await expect(page.getByRole('link', { name: 'Перейти до каталогу' })).toHaveAttribute('href', '/ua');
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow');
    });

    test('иконки чата нет, опрос messages/unread-count не выполняется', async ({ page }) => {
      await expectNoRequest(
        page,
        (r) => r.url().includes('/api/v1/messages/unread-count/'),
        async () => {
          await page.goto('/me');
          await expect(page.getByRole('link', { name: 'Сповіщення' }).first()).toBeVisible();
        },
      );
      await expect(page.getByRole('banner').locator('a[href="/me/messages"]')).toHaveCount(0);
      await expect(page.locator('main a[href="/me/deals"]')).toHaveCount(0);
      await expect(page.locator('main a[href="/me/saved-searches"]')).toHaveCount(0);
    });

    test('API: подача 403, оплата 404, переписка 404', async ({ api }) => {
      const buyer = await api('buyer');
      const post = await buyer.post('/api/v1/local/listings/', { data: {} });
      expect(post.status()).toBe(403);
      expect(await post.json()).toEqual({ detail: 'Подача оголошень поки закрита' });
      expect((await buyer.post('/api/v1/payments/liqpay/checkout/', { data: {} })).status()).toBe(404);
      expect((await buyer.get('/api/v1/messages/conversations/')).status()).toBe(404);
    });

    test('загрузка фото от buyer → 403', async ({ api }) => {
      test.skip(listingId === null, 'в каталоге нет объявлений');
      const buyer = await api('buyer');
      const res = await buyer.post(`/api/v1/local/listings/${listingId}/images/`, {
        multipart: { image: { name: 'x.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('x') } },
      });
      expect(res.status()).toBe(403);
    });

    test('авторизованный видит кнопку «Показати телефон»', async ({ page }) => {
      test.skip(listingId === null, 'в каталоге нет объявлений');
      await page.goto(`/local/${listingId}`);
      await expect(page.getByRole('button', { name: 'Показати телефон' })).toBeVisible();
    });
  });
});

test.describe('Полный режим (ВОЛНА-2: оба флага on)', () => {
  test.beforeEach(() => {
    test.skip(mode !== 'full', `стек в режиме "${mode}", блок только для обоих флагов on`);
  });
  test.use({ storageState: GUEST });

  test('в шапке есть «Каталог Україна», /ua показывает «Подати оголошення» @smoke', async ({ page }) => {
    await page.goto('/ua');
    await expect(page.getByRole('banner').getByRole('link', { name: 'Каталог Україна' })).toHaveAttribute('href', '/ua');
    await expect(page.getByRole('link', { name: /Подати оголошення/ })).toBeVisible();
  });

  test('sitemap содержит /ua', async ({ request }) => {
    expect(await (await request.get('/sitemap.xml')).text()).toContain('/ua');
  });

  test('карточка: гость видит приглашение войти', async ({ page }) => {
    test.skip(listingId === null, 'в каталоге нет объявлений');
    await page.goto(`/local/${listingId}`);
    await expect(page.getByRole('link', { name: 'Увійдіть, щоб побачити телефон' })).toHaveAttribute('href', '/login');
  });
});
