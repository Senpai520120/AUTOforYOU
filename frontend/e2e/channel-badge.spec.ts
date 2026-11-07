/**
 * E2E: бейдж «від @канал» (задача 9.57): картка каталогу /ua і сторінка оголошення.
 * Дані: e2e_seed кладе в активне [E2E]-оголошення source_channel=afy_e2e_channel. Режим стека (C2C) читається з API.
 */
import { test, expect } from './fixtures';

test.use({ storageState: { cookies: [], origins: [] } });

const CHANNEL = 'afy_e2e_channel';
let c2c = false;
let listingId = 0;

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  c2c = (await (await ctx.get('/api/v1/site-settings/')).json()).c2c_enabled === true;
  if (c2c) {
    const body = await (await ctx.get('/api/v1/local/listings/?page_size=100')).json();
    const hit = (body.results as { id: number; source_channel?: string }[]).find((l) => l.source_channel === CHANNEL);
    listingId = hit?.id ?? 0;
  }
  await ctx.dispose();
});

test.describe('Бейдж «від @канал»', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!c2c || !listingId, 'розділ оголошень вимкнено або немає seed-оголошення з каналом');
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('каталог: у картки є бейдж-посилання на t.me з rel nofollow noopener', async ({ page }) => {
    await page.goto('/ua');
    const badge = page.getByTestId('channel-badge').first();
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText(`від @${CHANNEL}`);
    await expect(badge).toHaveAttribute('href', `https://t.me/${CHANNEL}`);
    await expect(badge).toHaveAttribute('target', '_blank');
    const rel = (await badge.getAttribute('rel')) ?? '';
    expect(rel.split(/\s+/)).toEqual(expect.arrayContaining(['nofollow', 'noopener']));
  });

  test('сторінка оголошення: той самий бейдж, телефону продавця немає', async ({ page }) => {
    await page.goto(`/local/${listingId}`);
    const badge = page.getByTestId('channel-badge');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute('href', `https://t.me/${CHANNEL}`);
    await expect(page.locator('a[href^="tel:"]')).toHaveCount(0);
  });
});

// Сторінка /local/[id] і каталог /ua рендеряться на сервері Next: page.route відповідь API там не підміняє.
// Тому некоректні імена перевіряються на чистій функції, з якої будується посилання бейджа.
test.describe('Бейдж «від @канал»: побудова посилання без браузера', () => {
  test('коректні імена дають лише https://t.me/<ім\'я>', async () => {
    const { channelUrl } = await import('../lib/channel');
    for (const ok of ['afy_news', 'A1b2c', 'a'.repeat(32)]) expect(channelUrl(ok)).toBe(`https://t.me/${ok}`);
  });

  test('порожні й некоректні значення не дають посилання', async () => {
    const { channelUrl } = await import('../lib/channel');
    const bad = ['', null, undefined, 'abcd', 'a'.repeat(33), '1abcde', 'javascript:alert(1)', 'evil.com/phish',
      '"><script>alert(1)</script>', 'https://t.me/abcde', '//evil.com', '@afy_news', 'afy news', 'afy_news\n',
      'абвгде', 'abc.def', 'afy-news'];
    for (const value of bad) expect(channelUrl(value as string | null | undefined), String(value)).toBeNull();
  });
});
