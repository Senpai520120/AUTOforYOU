/**
 * E2E: тексти й контакти з налаштувань, єдина українська мова (задача 6.4).
 * Підвал, /rules, /refund рендеряться на сервері (page.route їх не перехоплює) — перевіряються на даних
 * стека (e2e_seed і .env.e2e); варіанти «тарифи перевірені» і «платежі вимкнено» — Django-тести site_settings.
 */
import { test, expect, storageStatePath } from './fixtures';

const GUEST = { cookies: [], origins: [] };
const RUSSIAN_ONLY = /[ыэъёЫЭЪЁ]/;

let settings: Record<string, unknown> = {};

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  settings = await (await ctx.get('/api/v1/site-settings/')).json();
  await ctx.dispose();
});

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Тексти з налаштувань', () => {
  test.use({ storageState: GUEST });

  test('підвал: телефон, email, адреса з налаштувань; без плейсхолдерів «[… — заповнити]»', async ({ page }) => {
    await page.goto('/');
    const footer = page.locator('footer');
    await expect(footer).toContainText(String(settings.phone));
    await expect(footer).toContainText(String(settings.support_email));
    await expect(footer).toContainText(String(settings.owner_address));
    // «[E2E]» — префікс фікстури в назві власника, тому шукаємо саме плейсхолдери 1.12.
    await expect(footer).not.toContainText('заповнити');
    expect(await footer.innerText()).not.toMatch(/\[[^\]]*—[^\]]*\]/);
  });

  test('«Тестові тарифи» — за признаком tariffs_demo (у підвалі й на головній)', async ({ page }) => {
    await page.goto('/');
    const expected = settings.tariffs_demo === false ? 0 : 1;
    await expect(page.getByTestId('footer-demo-tariffs')).toHaveCount(expected);
    await expect(page.getByTestId('home-demo-tariffs')).toHaveCount(expected);
  });

  test('головна: без чисел ставок і назв портів', async ({ page }) => {
    await page.goto('/');
    const section = page.getByRole('region', { name: 'Що входить у розрахунок' });
    await expect(section).not.toContainText('%');
    await expect(section).not.toContainText('Клайпед');
    await expect(section).not.toContainText('buyer fee');
  });

  test('/rules: ліміт і строк з конфігурації, без {LOCAL_LISTING_MAX_ACTIVE}', async ({ page }) => {
    await page.goto('/rules');
    await expect(page.getByTestId('rules-max-active')).toContainText(String(settings.local_listing_max_active));
    await expect(page.getByTestId('rules-expiry')).toContainText(`${settings.local_listing_expiry_days} днів`);
    await expect(page.locator('main')).not.toContainText('{LOCAL_LISTING_MAX_ACTIVE}');
  });

  test('/refund: таблиця з тарифів API при увімкнених платежах, інакше — «недоступні»', async ({ page, request }) => {
    await page.goto('/refund');
    if (settings.payments_enabled === true) {
      const tariffs = await (await request.get('/api/v1/local/tariffs/')).json();
      test.skip(tariffs.length === 0, 'у фікстурі немає тарифів просування');
      const table = page.getByTestId('refund-tariffs');
      for (const t of tariffs) await expect(table).toContainText(t.name);
    } else {
      await expect(page.getByTestId('refund-payments-off')).toContainText('Платні послуги наразі недоступні');
      await expect(page.getByTestId('refund-tariffs')).toHaveCount(0);
    }
  });
});

test.describe('Telegram: імʼя бота з API', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('бот налаштований — посилання й імʼя з відповіді link-token', async ({ page }) => {
    await page.route('**/api/v1/telegram/link-token/', (r) => r.fulfill({
      json: { configured: true, bot_username: 'test_bot', token: 'x', link: 'https://t.me/test_bot?start=link_x',
        expires_at: new Date(Date.now() + 30 * 60_000).toISOString() },
    }));
    await page.goto('/me/telegram');
    await page.getByRole('button', { name: "Прив'язати Telegram" }).click();
    await expect(page.getByRole('link', { name: /@test_bot/ })).toHaveAttribute('href', 'https://t.me/test_bot?start=link_x');
    await expect(page.locator('body')).not.toContainText('AUTO_F_Y' + '_bot');  // колишній захардкоджений бот (08-C4)
  });

  test('бот не налаштований — «ще не налаштований», без посилання на t.me', async ({ page }) => {
    await page.route('**/api/v1/telegram/link-token/', (r) => r.fulfill({
      json: { configured: false, bot_username: null, token: null, link: null, expires_at: null },
    }));
    await page.goto('/me/telegram');
    await page.getByRole('button', { name: "Прив'язати Telegram" }).click();
    await expect(page.getByText('Telegram-бот ще не налаштований')).toBeVisible();
    await expect(page.locator('main a[href^="https://t.me/"]')).toHaveCount(0);
  });
});

test.describe('Мова інтерфейсу', () => {
  for (const path of ['/', '/ua', '/rules', '/refund']) {
    test(`${path}: немає російських літер`, async ({ page }) => {
      await page.goto(path);
      expect(await page.locator('body').innerText()).not.toMatch(RUSSIAN_ONLY);
    });
  }

  test('/calculator після розрахунку: немає російських літер', async ({ page }) => {
    await page.goto('/calculator');
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await expect(page.getByTestId('calc-result')).toBeVisible();
    expect(await page.locator('body').innerText()).not.toMatch(RUSSIAN_ONLY);
  });

  test.describe('кабінет', () => {
    test.use({ storageState: storageStatePath('buyer') });
    for (const path of ['/me', '/me/saved-searches', '/me/notifications', '/me/trusted-shops']) {
      test(`${path}: немає російських літер`, async ({ page }) => {
        await page.goto(path);
        await expect(page.locator('main')).toBeVisible();
        expect(await page.locator('body').innerText()).not.toMatch(RUSSIAN_ONLY);
      });
    }
  });
});
