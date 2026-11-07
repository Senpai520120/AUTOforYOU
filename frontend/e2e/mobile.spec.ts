/**
 * E2E: мобільний smoke (mobile-chrome та mobile-safari, див. playwright.config.ts).
 * 23-P43 (навігація, повідомлення, відсутність горизонтального скролу) та 23-P44 (форми) — задача 6.1.
 */
import type { Page } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

type Flags = { c2c_enabled: boolean; c2c_public_posting_enabled: boolean };
let flags: Flags;

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  const res = await ctx.get('/api/v1/site-settings/');
  expect(res.status()).toBe(200);
  flags = await res.json();
  await ctx.dispose();
});

const VIEWPORT = { width: 375, height: 812 };

// WebKit: layout динамічний (6.7), гідратація може скинути вже введене значення —
// повторюємо, доки обидва поля не тримають значення.
async function fillLogin(page: Page, emailValue: string, passwordValue: string) {
  const email = page.locator('input[type="email"]');
  const pass = page.locator('input[type="password"]');
  await expect(async () => {
    await email.fill(emailValue);
    await pass.fill(passwordValue);
    await expect(email).toHaveValue(emailValue, { timeout: 500 });
    await expect(pass).toHaveValue(passwordValue, { timeout: 500 });
  }).toPass();
}

// Гідратація може з'їсти перший клік — повторюємо, доки меню не відкрилось.
async function openMenu(page: Page) {
  const burger = page.getByRole('button', { name: 'Меню' });
  await expect(async () => {
    if ((await burger.getAttribute('aria-expanded')) !== 'true') await burger.click();
    await expect(burger).toHaveAttribute('aria-expanded', 'true', { timeout: 500 });
  }).toPass();
  return page.getByRole('navigation', { name: 'Мобільне меню' });
}

async function noHorizontalScroll(page: Page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
}

const postingOpen = () => flags.c2c_enabled && flags.c2c_public_posting_enabled;

test.describe('Мобільний smoke @mobile', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  for (const [path, heading] of [
    ['/', 'Авто з США під ключ в Україну'],
    ['/ua', 'Каталог Україна'],
    ['/calculator', 'Калькулятор вартості «під ключ»'],
  ] as const) {
    test(`${path} відкривається, h1 видно`, async ({ page }) => {
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(200);
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
    });
  }

  test('розрахунок у калькуляторі проходить', async ({ page }) => {
    await page.goto('/calculator');
    await page.getByLabel('Ціна аукціону ($)', { exact: true }).fill('5000');
    await page.getByLabel("Об'єм двигуна (см³)", { exact: true }).fill('2000');
    await page.getByLabel('Рік випуску', { exact: true }).fill('2018');
    await page.getByRole('button', { name: 'Розрахувати' }).click();

    await expect(page.getByRole('heading', { name: 'Деталізація вартості «під ключ»' })).toBeVisible();
    const total = page.getByRole('row').filter({ hasText: 'РАЗОМ' });
    await expect(total).toBeVisible();
    await expect(total).not.toContainText('—');
  });

  test('вхід на мобільному → /me', async ({ page }) => {
    const password = process.env.E2E_PASSWORD;
    if (!password) throw new Error('E2E_PASSWORD не задано.');
    await page.goto('/login');
    await fillLogin(page, 'buyer@e2e.test', password);
    await page.getByRole('button', { name: 'Увійти' }).click();

    await expect(page).toHaveURL(/\/me$/);
    await expect(page.getByText('buyer@e2e.test').first()).toBeVisible();
  });

  test('невірний пароль на мобільному → повідомлення, лишаємось на /login', async ({ page }) => {
    await page.goto('/login');
    await fillLogin(page, 'buyer@e2e.test', 'definitely-wrong-password');
    await page.getByRole('button', { name: 'Увійти' }).click();

    await expect(page.getByText('Невірний email або пароль')).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test('08-Q4: бургер → «Калькулятор» веде на сторінку, меню закривається', async ({ page }) => {
    await page.goto('/');
    const menu = await openMenu(page);
    await menu.getByRole('link', { name: 'Калькулятор' }).click();
    await expect(page).toHaveURL(/\/calculator$/);
    await expect(page.getByRole('button', { name: 'Меню' })).toHaveAttribute('aria-expanded', 'false');
  });

  test('08-Q4: пункт «Каталог Україна» у бургері залежить від прапорця C2C', async ({ page }) => {
    await page.goto('/');
    const menu = await openMenu(page);
    await expect(menu.getByRole('link', { name: 'Калькулятор' })).toBeVisible();
    await expect(menu.getByRole('link', { name: 'Каталог Україна' })).toHaveCount(flags.c2c_enabled ? 1 : 0);
    await expect(menu.getByRole('link', { name: 'Увійти' })).toBeVisible();
    await expect(menu.getByRole('link', { name: 'Реєстрація' })).toBeVisible();
  });

  test('08-Q4: Esc закриває меню, повторне натискання теж', async ({ page }) => {
    await page.goto('/');
    await openMenu(page);
    const burger = page.getByRole('button', { name: 'Меню' });
    await page.keyboard.press('Escape');
    await expect(burger).toHaveAttribute('aria-expanded', 'false');
    await openMenu(page);
    await burger.click();
    await expect(burger).toHaveAttribute('aria-expanded', 'false');
  });

  // /listings не перевіряємо: на ВОЛНІ-1 лоти вимкнені (LOTS_ENABLED=false, задача 2.8) і віддають 404.
  for (const path of ['/', '/calculator', '/login', '/register']) {
    test(`23-P43: ${path} на 375 px без горизонтального скролу`, async ({ page }) => {
      await page.setViewportSize(VIEWPORT);
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(200);
      await noHorizontalScroll(page);
    });
  }

  test('23-P43: /ua на 375 px без горизонтального скролу (якщо C2C увімкнено)', async ({ page }) => {
    test.skip(!flags.c2c_enabled, 'C2C вимкнено (E2E_C2C=off)');
    await page.setViewportSize(VIEWPORT);
    await page.goto('/ua');
    await noHorizontalScroll(page);
  });

  test('23-P44: калькулятор на 375 px — розрахунок, розбивка у власному контейнері', async ({ page }) => {
    await page.setViewportSize(VIEWPORT);
    await page.goto('/calculator');
    await page.getByLabel('Ціна аукціону ($)', { exact: true }).fill('5000');
    await page.getByLabel("Об'єм двигуна (см³)", { exact: true }).fill('2000');
    await page.getByLabel('Рік випуску', { exact: true }).fill('2018');
    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await expect(page.getByRole('row').filter({ hasText: 'РАЗОМ' })).toBeVisible();
    await expect(page.getByTestId('calc-breakdown-scroll')).toBeVisible();
    await noHorizontalScroll(page);
  });
});

test.describe('Мобільний кабінет buyer @mobile', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
    await page.setViewportSize(VIEWPORT);
  });

  test('23-P43: у меню є «Кабінет» і «Вийти», без горизонтального скролу', async ({ page }) => {
    await page.goto('/me');
    await expect(page.getByText('buyer@e2e.test').first()).toBeVisible();
    await noHorizontalScroll(page);
    const menu = await openMenu(page);
    await expect(menu.getByRole('link', { name: 'Кабінет' })).toBeVisible();
    await expect(menu.getByRole('button', { name: 'Вийти' })).toBeVisible();
    await noHorizontalScroll(page);
  });

  test('23-P43: /me/messages — список, тред на всю ширину, «← Діалоги» повертає до списку', async ({ page }) => {
    test.skip(!postingOpen(), 'Переписка відкрита лише в повному режимі C2C');
    await page.goto('/me/messages');
    const conv = page.getByRole('button', { name: /Користувач/ });
    await expect(conv).toBeVisible();
    await noHorizontalScroll(page);

    await conv.click();
    await expect(page.getByRole('link', { name: 'Переглянути оголошення →' })).toBeVisible();
    await expect(conv).toBeHidden();
    await noHorizontalScroll(page);

    await page.getByRole('button', { name: '← Діалоги' }).click();
    await expect(conv).toBeVisible();
    await expect(page.getByRole('link', { name: 'Переглянути оголошення →' })).toBeHidden();
  });

  test('23-P44: /local/new — кнопка видалення фото видна без hover і видаляє фото', async ({ page }) => {
    test.skip(!postingOpen(), 'Подача відкрита лише в повному режимі C2C');
    await page.goto('/local/new');
    await expect(page.getByRole('heading', { name: 'Подати оголошення' })).toBeVisible();
    await noHorizontalScroll(page);

    const png = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
      'base64',
    );
    await page.locator('input[type="file"]').setInputFiles({ name: 'e2e.png', mimeType: 'image/png', buffer: png });
    const del = page.getByRole('button', { name: 'Видалити фото' });
    await expect(del).toBeVisible();
    await expect(del).toHaveCSS('opacity', '1');
    const box = await del.boundingBox();
    expect(box!.width).toBeGreaterThanOrEqual(32);
    await del.click();
    await expect(del).toHaveCount(0);
  });

  test('23-P44: /local/new — порожня форма не відправляється, поля в межах екрана', async ({ page }) => {
    test.skip(!postingOpen(), 'Подача відкрита лише в повному режимі C2C');
    await page.goto('/local/new');
    const make = page.getByPlaceholder('Toyota');
    await expect(make).toBeVisible();
    let posted = false;
    page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/local/listings')) posted = true; });
    await page.locator('form button[type="submit"]').click();
    await expect.poll(() => make.evaluate((el: HTMLInputElement) => el.validity.valueMissing)).toBe(true);
    expect(posted).toBe(false);
    const box = await make.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(VIEWPORT.width);
    await noHorizontalScroll(page);
  });
});
