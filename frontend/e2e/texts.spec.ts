/**
 * E2E: тексти та контакти з налаштувань, єдина українська мова (задача 6.4).
 *
 * Серверні сторінки (/rules, /refund, підвал, головна) беруть дані з API на сервері Next, тому
 * page.route їх не перехоплює: значення порівнюються з відповіддю того самого API (request),
 * а стани, які потребують іншого .env (PAYMENTS_ENABLED=false) або порожніх налаштувань, —
 * test.fixme з посиланням на задачу. Клієнтські запити (/me/telegram) емулюються через page.route.
 */
import { test, expect, storageStatePath } from './fixtures';

const API = process.env.E2E_API_URL ?? 'http://localhost';
const RU = /[ыэъё]/;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Гість: контакти та налаштування', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('успіх: підвал показує телефон, email і адресу з налаштувань (сид e2e)', async ({ page }) => {
    // Підвал кешує налаштування 60 с: якщо «/» відкрили до e2e_seed (перевірка готовності стеку),
    // перша хвилина може віддати порожні реквізити — перезавантажуємо, доки кеш не оновиться.
    test.setTimeout(120_000);
    const requisites = page.getByTestId('footer-requisites');
    await expect(async () => {
      await page.goto('/');
      await expect(requisites).toContainText('+380500000000', { timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await expect(requisites).toContainText('support@e2e.test');
    await expect(requisites).toContainText('вул. Тестова, 1');
  });

  test('обхід: у підвалі немає плейсхолдерів «[… — заповнити]»', async ({ page }) => {
    await page.goto('/');
    const footer = page.locator('footer');
    await expect(footer).toContainText('AUTOforYOU');
    const text = await footer.innerText();
    expect(text).not.toContain('заповнити');
    expect(text).not.toMatch(/\[[^\]]*(…|\.\.\.)[^\]]*\]/);
  });

  test.fixme('обхід: порожні контакти — рядок реквізитів не виводиться (6.4 → потрібен стек з порожніми SiteSettings)', async () => {});

  test('успіх: /rules підставляє ліміти з конфігурації й не містить літералу', async ({ page, request }) => {
    const cfg = await (await request.get(`${API}/api/v1/site-settings/`)).json();
    await page.goto('/rules');
    const body = await page.locator('body').innerText();
    expect(body).not.toContain('{LOCAL_LISTING_MAX_ACTIVE}');
    expect(body).toContain(`не більше ${cfg.local_listing_max_active} активних оголошень`);
    expect(body).toMatch(new RegExp(`діє ${cfg.local_listing_expiry_days} (день|дні|днів) з моменту схвалення модератором`));
    expect(body).not.toContain('30 днів з моменту публікації');
  });

  test('успіх: /refund показує тарифи з API при увімкнених платежах', async ({ page, request }) => {
    const cfg = await (await request.get(`${API}/api/v1/site-settings/`)).json();
    test.skip(cfg.payments_enabled !== true, 'PAYMENTS_ENABLED=false: таблиці немає, див. наступний тест');
    const tariffs = await (await request.get(`${API}/api/v1/local/tariffs/`)).json();
    expect(tariffs.length).toBeGreaterThan(0);
    await page.goto('/refund');
    const table = page.getByTestId('refund-tariffs');
    await expect(table).toBeVisible();
    for (const t of tariffs) await expect(table).toContainText(t.name);
  });

  test('обхід: /refund при PAYMENTS_ENABLED=false — повідомлення замість таблиці', async ({ page, request }) => {
    const cfg = await (await request.get(`${API}/api/v1/site-settings/`)).json();
    test.skip(cfg.payments_enabled === true, 'стек з PAYMENTS_ENABLED=true; потрібен стек з false (6.4)');
    await page.goto('/refund');
    await expect(page.getByTestId('refund-payments-off')).toContainText('Платні послуги наразі недоступні');
    await expect(page.getByTestId('refund-tariffs')).toHaveCount(0);
  });

  test('успіх: позначка «Тестові тарифи» на головній і в підвалі збігається з is_demo з API', async ({ page, request }) => {
    const rates = await (await request.get(`${API}/api/v1/pricing/rates/`)).json();
    await page.goto('/');
    const expected = rates.is_demo === true ? 1 : 0;
    await expect(page.getByTestId('home-demo-note')).toHaveCount(expected);
    await expect(page.getByTestId('footer-demo-note')).toHaveCount(expected);
  });

  test('обхід: на головній немає цифр ставок і назв портів', async ({ page }) => {
    await page.goto('/');
    const text = await page.locator('main').innerText();
    for (const bad of ['50–150', 'Мито 10%', 'ПДВ 20%', 'Клайпед', 'Гданськ', 'buyer fee', 'virtual bid']) {
      expect(text).not.toContain(bad);
    }
    await expect(page.getByText('Акциз — залежить від палива')).toBeVisible();
  });
});

test.describe('Покупець: /me/telegram і /me/shipments', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('успіх: ім’я бота і «діє до HH:MM» беруться з відповіді link-token', async ({ page }) => {
    await page.route('**/api/v1/telegram/link-token/', (route) =>
      route.fulfill({
        json: {
          configured: true,
          bot_username: 'e2e_texts_bot',
          token: '00000000-0000-0000-0000-000000000002',
          expires_at: new Date(Date.now() + 30 * 60000).toISOString(),
          link: 'https://t.me/e2e_texts_bot?start=link_00000000-0000-0000-0000-000000000002',
          note: 'x',
        },
      }),
    );
    await page.goto('/me/telegram');
    await page.getByRole('button', { name: 'Прив\'язати Telegram' }).click();
    await expect(page.getByRole('link', { name: /Відкрити @e2e_texts_bot у Telegram/ })).toBeVisible();
    await expect(page.getByText(/Посилання діє до \d{2}:\d{2}/)).toBeVisible();
  });

  test('помилка: link: null — «ще не налаштований» і немає посилання з t.me/?start', async ({ page }) => {
    await page.route('**/api/v1/telegram/link-token/', (route) =>
      route.fulfill({
        json: { configured: false, bot_username: null, token: null, expires_at: null, link: null, note: null },
      }),
    );
    await page.goto('/me/telegram');
    await page.getByRole('button', { name: 'Прив\'язати Telegram' }).click();
    await expect(page.getByText('ще не налаштований')).toBeVisible();
    await expect(page.locator('a[href^="https://t.me/?"], a[href="https://t.me/"]')).toHaveCount(0);
  });

  // /me/shipments — замороженій модуль (2.8): без SHIPMENTS_ENABLED сторінка дає 404.
  test('успіх: порожній стан контейнерів показує контакт менеджера з налаштувань', async ({ page, request }) => {
    const cfg = await (await request.get(`${API}/api/v1/site-settings/`)).json();
    test.skip(cfg.shipments_enabled !== true, 'SHIPMENTS_ENABLED=false: /me/shipments віддає 404 (2.8)');
    await page.route('**/api/v1/me/shipments/**', (route) => route.fulfill({ json: { count: 0, results: [] } }));
    await page.route('**/api/v1/site-settings/', (route) =>
      route.fulfill({ json: { manager_contact: '+380670000001 (E2E менеджер)' } }),
    );
    await page.goto('/me/shipments');
    await expect(page.getByText('Зверніться до менеджера, щоб додати контейнер: +380670000001 (E2E менеджер)')).toBeVisible();
  });

  test('обхід: без контакту менеджера — текст без виду «: » і без вигаданого номера', async ({ page, request }) => {
    const cfg = await (await request.get(`${API}/api/v1/site-settings/`)).json();
    test.skip(cfg.shipments_enabled !== true, 'SHIPMENTS_ENABLED=false: /me/shipments віддає 404 (2.8)');
    await page.route('**/api/v1/me/shipments/**', (route) => route.fulfill({ json: { count: 0, results: [] } }));
    await page.route('**/api/v1/site-settings/', (route) => route.fulfill({ json: { manager_contact: '' } }));
    await page.goto('/me/shipments');
    const hint = page.getByText('Зверніться до менеджера, щоб додати контейнер', { exact: true });
    await expect(hint).toBeVisible();
  });
});

test.describe('Мова інтерфейсу', () => {
  test.use({ storageState: storageStatePath('buyer') });

  const PUBLIC = ['/', '/listings', '/ua', '/calculator', '/rules', '/refund'];
  for (const url of PUBLIC) {
    test(`немає російських літер [ыэъё]: ${url}`, async ({ page }) => {
      await page.goto(url);
      await expect(page.locator('h1').first()).toBeVisible();
      expect(await page.locator('body').innerText()).not.toMatch(RU);
    });
  }

  for (const url of ['/me', '/me/telegram', '/me/saved-searches', '/me/trusted-shops']) {
    test(`немає російських літер [ыэъё]: ${url}`, async ({ page }) => {
      await page.goto(url);
      await expect(page.locator('main')).toBeVisible();
      expect(await page.locator('body').innerText()).not.toMatch(RU);
    });
  }

  test('шапка не містить «Перекупам UA»', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('header')).not.toContainText('Перекупам');
  });
});
