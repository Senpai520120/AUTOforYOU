/**
 * E2E: доступність і швидкість клієнта (задача 6.5; 23-P47).
 * axe (WCAG 2.0 A/AA): 0 порушень serious/critical; клавіатура, модалка, видимий фокус, alt,
 * пауза опитування на прихованій вкладці, відсутність втрати фокусу в /me/deals.
 * Сторінки з C2C-даними пропускаються, якщо розділ вимкнено або немає даних e2e_seed.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

type Flags = { c2c_enabled: boolean; c2c_public_posting_enabled: boolean };
let flags: Flags;
let listingId: number | null = null;

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  const res = await ctx.get('/api/v1/site-settings/');
  expect(res.status()).toBe(200);
  flags = await res.json();
  const list = await ctx.get('/api/v1/local/listings/');
  if (list.ok()) listingId = (await list.json()).results?.[0]?.id ?? null;
  await ctx.dispose();
});

const GUEST = { cookies: [], origins: [] };
const postingOpen = () => flags.c2c_enabled && flags.c2c_public_posting_enabled;
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
);

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

async function serious(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  return violations
    .filter(v => v.impact === 'serious' || v.impact === 'critical')
    .map(v => `${v.id} [${v.impact}]: ${v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | ')}`);
}

// Серверний кеш до e2e_seed: перезавантаження, доки з'явиться основний вміст.
async function openReady(page: Page, path: string, ready: () => Promise<void>) {
  await expect(async () => {
    await page.goto(path);
    await ready();
  }).toPass();
}

const h1 = (page: Page) => page.getByRole('heading', { level: 1 }).first();

test.describe('23-P47: axe, гість', () => {
  test.use({ storageState: GUEST });
  for (const path of ['/', '/login', '/register', '/calculator', '/ua']) {
    test(`${path}: немає порушень serious/critical`, async ({ page }) => {
      await openReady(page, path, () => expect(h1(page)).toBeVisible({ timeout: 3000 }));
      expect(await serious(page)).toEqual([]);
    });
  }
  test('мобільний: /login, /register, /calculator, /ua @mobile', async ({ page }) => {
    for (const path of ['/login', '/register', '/calculator', '/ua']) {
      await openReady(page, path, () => expect(h1(page)).toBeVisible({ timeout: 3000 }));
      expect(await serious(page), path).toEqual([]);
    }
  });
});

test.describe('23-P47: axe, buyer', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('/me: немає порушень serious/critical', async ({ page }) => {
    await page.goto('/me');
    await expect(h1(page)).toBeVisible();
    expect(await serious(page)).toEqual([]);
  });

  test('/local/new: немає порушень serious/critical', async ({ page }) => {
    test.skip(!postingOpen(), 'Подача відкрита лише в повному режимі C2C');
    await page.goto('/local/new');
    await expect(page.getByLabel('Марка')).toBeVisible();
    expect(await serious(page)).toEqual([]);
  });

  test('мобільний: /me @mobile', async ({ page }) => {
    await page.goto('/me');
    await expect(h1(page)).toBeVisible();
    expect(await serious(page)).toEqual([]);
  });
});

test.describe('23-P47: форма входу з клавіатури', () => {
  test.use({ storageState: GUEST });

  test('Tab/ввід/Enter, неправильний пароль → role=alert, label↔input', async ({ page }) => {
    await page.goto('/login');
    const email = page.getByLabel('Email');
    const password = page.getByLabel('Пароль', { exact: true });
    await expect(email).toBeVisible();
    await expect(password).toBeVisible();

    // Гідратація може скинути введене — повторюємо, доки значення тримається.
    await expect(async () => {
      await email.focus();
      await page.keyboard.press('Control+A');
      await page.keyboard.type('nobody@e2e.test');
      await page.keyboard.press('Tab');
      await expect(password).toBeFocused({ timeout: 500 });
      await page.keyboard.press('Control+A');
      await page.keyboard.type('wrong-password-1');
      await expect(email).toHaveValue('nobody@e2e.test', { timeout: 500 });
    }).toPass();
    await page.keyboard.press('Enter');
    await expect(page.locator('form [role="alert"]')).toHaveText(/\S/);
  });
});

test.describe('Модальне вікно (Modal)', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('«Поскаржитися»: фокус всередині, Tab не виходить, Esc закриває, фокус повертається', async ({ page }) => {
    test.skip(listingId === null, 'в каталозі немає оголошень (запустіть e2e_seed)');
    test.skip(!postingOpen(), 'Кнопка скарги є лише в повному режимі C2C');
    await page.goto(`/local/${listingId}`);
    const trigger = page.getByRole('button', { name: 'Поскаржитися' });
    await expect(trigger).toBeVisible();
    await trigger.click();

    const dialog = page.getByRole('dialog', { name: 'Поскаржитися' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
    await expect(dialog.locator(':focus')).toHaveCount(1);
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press('Tab');
      await expect(dialog.locator(':focus')).toHaveCount(1);
    }
    await page.keyboard.press('Shift+Tab');
    await expect(dialog.locator(':focus')).toHaveCount(1);

    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test('«Поскаржитися»: клік по підкладці закриває вікно', async ({ page }) => {
    test.skip(listingId === null, 'в каталозі немає оголошень (запустіть e2e_seed)');
    test.skip(!postingOpen(), 'Кнопка скарги є лише в повному режимі C2C');
    await page.goto(`/local/${listingId}`);
    await page.getByRole('button', { name: 'Поскаржитися' }).click();
    const dialog = page.getByRole('dialog', { name: 'Поскаржитися' });
    await expect(dialog).toBeVisible();
    await page.mouse.click(5, 5);
    await expect(dialog).toHaveCount(0);
  });
});

test.describe('Видимий фокус і alt', () => {
  test.use({ storageState: GUEST });

  for (const path of ['/login', '/ua']) {
    test(`${path}: після Tab у сфокусованого елемента є контур або тінь`, async ({ page }) => {
      await page.goto(path);
      await expect(h1(page)).toBeVisible();
      for (let i = 0; i < 4; i++) {
        await page.keyboard.press('Tab');
        const style = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement;
          const cs = getComputedStyle(el);
          return { tag: el.tagName, outline: cs.outlineStyle, width: cs.outlineWidth, shadow: cs.boxShadow };
        });
        expect(style.tag).not.toBe('BODY');
        expect(style.outline !== 'none' || style.shadow !== 'none', JSON.stringify(style)).toBe(true);
      }
    });
  }

  test('/ua: у зображень каталогу змістовний alt, перше не lazy', async ({ page }) => {
    test.skip(listingId === null, 'в каталозі немає оголошень (запустіть e2e_seed)');
    await openReady(page, '/ua', () => expect(page.locator('article img').first()).toBeVisible({ timeout: 3000 }));
    const imgs = page.locator('article img');
    const alts = await imgs.evaluateAll(els => els.map(e => e.getAttribute('alt')));
    expect(alts.length).toBeGreaterThan(0);
    for (const alt of alts) {
      expect(alt).not.toBeNull();
      expect(alt!.toLowerCase()).not.toBe('фото');
      expect(alt!).not.toMatch(/\.(jpe?g|png|webp)$/i);
    }
    await expect(imgs.first()).not.toHaveAttribute('loading', 'lazy');
    await expect(imgs.first()).toHaveAttribute('fetchpriority', 'high');
  });
});

test.describe('Форма оголошення: фото', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('імя файлу не потрапляє в alt; додати й видалити 3 фото — без помилок у консолі', async ({ page }) => {
    test.skip(!postingOpen(), 'Подача відкрита лише в повному режимі C2C');
    const errors: string[] = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', e => errors.push(String(e)));

    await page.goto('/local/new');
    await expect(page.getByLabel('Марка')).toBeVisible();
    const files = [
      { name: 'IMG_0001.jpg', mimeType: 'image/jpeg', buffer: PNG },
      { name: 'IMG_0002.png', mimeType: 'image/png', buffer: PNG },
      { name: 'IMG_0003.webp', mimeType: 'image/webp', buffer: PNG },
    ];
    await page.locator('input[type="file"]').setInputFiles(files);

    const thumbs = page.locator('img[alt^="Фото"]');
    await expect(thumbs).toHaveCount(3);
    const alts = await thumbs.evaluateAll(els => els.map(e => e.getAttribute('alt')));
    expect(alts).toEqual(['Фото 1 з 3', 'Фото 2 з 3', 'Фото 3 з 3']);

    const del = page.getByRole('button', { name: 'Видалити фото' });
    for (let left = 3; left > 0; left--) {
      await del.first().click();
      await expect(del).toHaveCount(left - 1);
    }
    expect(errors).toEqual([]);
  });
});

test.describe('Опитування на прихованій вкладці', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('/me: hidden → жодного unread-count за 60 с; visible → запит одразу', async ({ page }) => {
    await page.clock.install();
    let unread = 0;
    page.on('request', r => { if (r.url().includes('/unread-count/')) unread++; });
    await page.goto('/me');
    await expect(h1(page)).toBeVisible();
    await expect.poll(() => unread).toBeGreaterThan(0);

    const setVisibility = (state: 'hidden' | 'visible') => page.evaluate((s) => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => s });
      document.dispatchEvent(new Event('visibilitychange'));
    }, state);

    await setVisibility('hidden');
    unread = 0;
    await page.clock.fastForward(30_000);
    await page.clock.fastForward(30_000);
    await page.waitForTimeout(500); // шанс небажаному запиту дійти до page.on('request')
    expect(unread).toBe(0);

    await setVisibility('visible');
    await expect.poll(() => unread).toBeGreaterThan(0);
  });
});

test.describe('/me/deals: фокус у полі відгуку', () => {
  test.use({ storageState: storageStatePath('buyer') });

  test('введення 20 символів не губить фокус', async ({ page, api }) => {
    test.skip(!postingOpen(), 'Угоди доступні лише в повному режимі C2C');
    const profile = await (await (await api('buyer')).get('/api/v1/auth/profile/')).json();
    const deal = {
      id: 987654, listing: { id: 1, make: 'Skoda', model: 'Octavia', year: 2018 },
      seller: { id: profile.id + 1000, display_name: '[E2E] Продавець' },
      buyer: { id: profile.id, display_name: '[E2E] Покупець' },
      status: 'confirmed', created_at: '2026-01-01T00:00:00Z', confirmed_at: '2026-01-02T00:00:00Z', review: null,
    };
    await page.route('**/api/v1/deals/', route => route.request().method() === 'GET'
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([deal]) })
      : route.fallback());
    await page.goto('/me/deals');
    const area = page.getByRole('textbox', { name: 'Відгук про продавця' });
    await expect(area).toBeVisible();
    await area.click();
    await page.keyboard.type('двадцять символів ok');
    await expect(area).toBeFocused();
    await expect(area).toHaveValue('двадцять символів ok');

    const group = page.getByRole('radiogroup', { name: 'Оцінка' });
    await group.getByRole('radio', { name: '4 з 5' }).click();
    await expect(group.getByRole('radio', { name: '4 з 5' })).toHaveAttribute('aria-checked', 'true');
    await expect(group.getByRole('radio', { name: '5 з 5' })).toHaveAttribute('aria-checked', 'false');
    await expect(area).toHaveValue('двадцять символів ok');
  });
});
