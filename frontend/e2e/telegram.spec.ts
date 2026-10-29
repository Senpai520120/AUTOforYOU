/**
 * E2E: прив'язка Telegram на /me/telegram (задача 5.4, 23-P41).
 *
 * Бот у e2e-стеку не налаштований, тому «налаштований» стан емулюється через page.route на
 * POST /api/v1/telegram/link-token/. Фактичну прив'язку (/start link_...) і /unlink в боті
 * перевіряють Django-тести telegram_bot.
 */
import { test, expect, storageStatePath } from './fixtures';

const LINK_TOKEN_URL = '**/api/v1/telegram/link-token/';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.describe('Гість', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('обхід: гостя з /me/telegram перекидає на /login', async ({ page }) => {
    await page.goto('/me/telegram');
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('Покупець без прив\'язки', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('успіх: посилання веде на бота з імені у відповіді API', async ({ page }) => {
    await page.route(LINK_TOKEN_URL, (route) => {
      expect(route.request().method()).toBe('POST');
      return route.fulfill({
        json: {
          configured: true,
          bot_username: 'e2e_demo_bot',
          token: '00000000-0000-0000-0000-000000000001',
          expires_at: new Date(Date.now() + 30 * 60000).toISOString(),
          link: 'https://t.me/e2e_demo_bot?start=link_00000000-0000-0000-0000-000000000001',
          note: 'x',
        },
      });
    });
    await page.goto('/me/telegram');
    await page.getByRole('button', { name: 'Прив\'язати Telegram' }).click();
    const link = page.getByRole('link', { name: /Відкрити @e2e_demo_bot у Telegram/ });
    await expect(link).toHaveAttribute('href', /^https:\/\/t\.me\/e2e_demo_bot\?start=link_/);
    await expect(page.getByText(/Посилання діє до \d{2}:\d{2}/)).toBeVisible();
  });

  test('помилка: бот не налаштований — повідомлення, посилання t.me немає', async ({ page }) => {
    await page.route(LINK_TOKEN_URL, (route) =>
      route.fulfill({
        json: { configured: false, bot_username: null, token: null, expires_at: null, link: null, note: null },
      }),
    );
    await page.goto('/me/telegram');
    await page.getByRole('button', { name: 'Прив\'язати Telegram' }).click();
    await expect(page.getByText('Telegram-бот ще не налаштований')).toBeVisible();
    // У футері є посилання на канал (t.me/e2e_channel із сиду) — перевіряємо саме посилання прив'язки.
    await expect(page.locator('a[href*="t.me/"][href*="start=link_"]')).toHaveCount(0);
  });

  test('помилка: 429 — зрозуміле повідомлення', async ({ page }) => {
    await page.route(LINK_TOKEN_URL, (route) =>
      route.fulfill({ status: 429, json: { detail: 'Request was throttled.' } }),
    );
    await page.goto('/me/telegram');
    await page.getByRole('button', { name: 'Прив\'язати Telegram' }).click();
    await expect(page.getByText('Забагато запитів')).toBeVisible();
  });
});

// Привязанный пользователь: фикстуры 0.4 не содержат Telegram-привязанного покупателя.
test.fixme('P41-linked: статус і «Відв\'язати Telegram» у прив\'язаного → 0.4 (фікстура з telegram_id)', async () => {});
