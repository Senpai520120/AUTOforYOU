/**
 * E2E: журнал згод (1.14) - «Налаштування cookie» у футері, JSON-вибір з версією,
 * сумісність зі старим значенням, повторна згода за версією, обхід 18+.
 */
import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';
import { expectNoRequest } from './helpers/network';
import { captchaToken } from './helpers/captcha';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

test.use({ storageState: { cookies: [], origins: [] } });

const BANNER = 'Налаштування файлів cookie';
const SETTINGS_URL = '**/api/v1/site-settings/';

// Банер читає публічні налаштування з браузера, тому їх можна підмінити через page.route.
const mockSettings = (page: Page, version: string, reconsent: boolean) =>
  page.route(SETTINGS_URL, async (route) => {
    const resp = await route.fetch();
    const body = await resp.json();
    await route.fulfill({
      response: resp,
      json: { ...body, legal_docs_version: version, legal_docs_reconsent_required: reconsent },
    });
  });

const rawConsent = (page: Page) => page.evaluate(() => localStorage.getItem('cookie_consent'));

// Функція серіалізується в браузер, тому замикань немає: дані передаються аргументом.
const seedConsent = (page: Page, level: string, version: string) =>
  page.addInitScript(
    (v) => localStorage.setItem('cookie_consent', JSON.stringify({ ...v, ts: '2026-01-01T00:00:00Z' })),
    { level, version },
  );

test.describe('Налаштування cookie у футері (1.14)', () => {
  for (const path of ['/', '/calculator', '/privacy']) {
    test(`кнопка у футері ${path}: відкриває панель, вибір зберігається як JSON з version`, async ({ page }) => {
      await mockSettings(page, '2026-10-01', false);
      await page.addInitScript(() => localStorage.setItem('cookie_consent', 'all'));
      await page.goto(path);
      const footerBtn = page.getByRole('contentinfo').getByRole('button', { name: 'Налаштування cookie' });
      await expect(footerBtn).toBeVisible();
      const banner = page.getByRole('dialog', { name: BANNER });
      await expect(banner).toHaveCount(0);
      await footerBtn.click();
      await expect(banner).toBeVisible();
      await expect(banner.getByTestId('cookie-current-choice')).toContainText('Прийняті всі');
      await banner.getByRole('button', { name: 'Лише необхідні' }).click();
      await expect(banner).toBeHidden();
      const value = JSON.parse((await rawConsent(page))!);
      expect(value.level).toBe('necessary');
      expect(value.version).toBe('2026-10-01');
      expect(typeof value.ts).toBe('string');
    });
  }

  test('панель закривається без зміни вибору', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('cookie_consent', 'necessary'));
    await page.goto('/');
    await page.getByRole('contentinfo').getByRole('button', { name: 'Налаштування cookie' }).click();
    const banner = page.getByRole('dialog', { name: BANNER });
    await banner.getByRole('button', { name: 'Закрити' }).click();
    await expect(banner).toBeHidden();
    expect(await rawConsent(page)).toBe('necessary');
  });
});

test.describe('Сумісність і повторна згода (1.14)', () => {
  test('старе значення "all": банер не з’являється, вибір не втрачено', async ({ page }) => {
    await mockSettings(page, '2026-10-01', false);
    await page.addInitScript(() => localStorage.setItem('cookie_consent', 'all'));
    const settingsLoaded = page.waitForResponse(SETTINGS_URL);
    await page.goto('/cookies');
    await settingsLoaded;
    await expect(page.locator('strong', { hasText: 'Прийняті всі' })).toBeVisible();
    await expect(page.getByRole('dialog', { name: BANNER })).toHaveCount(0);
    expect(await rawConsent(page)).toBe('all');
  });

  test('нова версія + reconsent_required=true: банер з’являється знову', async ({ page }) => {
    await mockSettings(page, 'v2', true);
    await seedConsent(page, 'all', 'v1');
    await page.goto('/');
    await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
  });

  test('нова версія + reconsent_required=false: вибір лишається', async ({ page }) => {
    await mockSettings(page, 'v2', false);
    await seedConsent(page, 'all', 'v1');
    const settingsLoaded = page.waitForResponse(SETTINGS_URL);
    await page.goto('/cookies');
    await settingsLoaded;
    await expect(page.locator('strong', { hasText: 'Прийняті всі' })).toBeVisible();
    await expect(page.getByRole('dialog', { name: BANNER })).toHaveCount(0);
  });

  test('та сама версія + reconsent_required=true: банера немає', async ({ page }) => {
    await mockSettings(page, 'v1', true);
    await seedConsent(page, 'necessary', 'v1');
    const settingsLoaded = page.waitForResponse(SETTINGS_URL);
    await page.goto('/cookies');
    await settingsLoaded;
    await expect(page.locator('strong', { hasText: 'Лише необхідні' })).toBeVisible();
    await expect(page.getByRole('dialog', { name: BANNER })).toHaveCount(0);
  });

  test('пошкоджений JSON: сторінка працює, банер як при першому візиті', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('cookie_consent', '{broken'));
    await page.goto('/');
    await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
    await expect(page.getByRole('contentinfo')).toBeVisible();
  });

  test('API налаштувань недоступне (500): банер працює без версії', async ({ page }) => {
    await page.route(SETTINGS_URL, (route) => route.fulfill({ status: 500, body: 'err' }));
    await page.goto('/');
    const banner = page.getByRole('dialog', { name: BANNER });
    await expect(banner).toBeVisible();
    await banner.getByRole('button', { name: 'Лише необхідні' }).click();
    await expect(banner).toBeHidden();
    const value = JSON.parse((await rawConsent(page))!);
    expect(value.level).toBe('necessary');
    expect(value.version).toBeNull();
  });
});

test.describe('Обхід 18+ (1.14)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('форма реєстрації без 18+ не відправляється', async ({ page, uniqueEmail }) => {
    await page.goto('/register');
    await page.fill('input[type="email"]', uniqueEmail);
    await page.locator('input[type="password"]').first().fill('StrongPass123!');
    await page.locator('input[type="password"]').nth(1).fill('StrongPass123!');
    await page.getByLabel(/Погоджуюсь з/).check();
    const isRegisterPost = (r: { url(): string; method(): string }) =>
      r.url().includes('/auth/register/') && r.method() === 'POST';
    await expectNoRequest(page, isRegisterPost, async () => {
      await page.getByRole('button', { name: 'Зареєструватися' }).click();
    });
  });

  test('прямий POST без confirmed_age_18 -> 400 з помилкою поля', async ({ request, uniqueEmail }) => {
    const resp = await request.post('/api/v1/auth/register/', {
      data: {
        email: uniqueEmail, password: 'StrongPass123!', password2: 'StrongPass123!',
        agreed_to_terms: true, captcha_token: await captchaToken(request),
      },
    });
    expect(resp.status()).toBe(400);
    expect(Object.keys(await resp.json())).toContain('confirmed_age_18');
    // Акаунт не створено: вхід цим email не проходить (401).
    const login = await request.post('/api/v1/auth/token/', {
      data: { email: uniqueEmail, password: 'StrongPass123!' },
    });
    expect(login.status()).toBe(401);
  });
});

test.describe('hasAnalyticsConsent і версія документів (1.14, без браузера)', () => {
  // Playwright в CI (Node 20) не вміє імпортувати ESM-модуль lib/consent.ts, тому
  // транспілюємо справжній вихідний файл у CommonJS і виконуємо його тут: тест
  // перевіряє реальний код, а не копію логіки.
  type ConsentModule = {
    registerLegalVersion: (v: string | null | undefined, reconsent?: boolean) => void;
    hasAnalyticsConsent: () => boolean;
  };
  const loadConsent = (): ConsentModule => {
    const src = readFileSync(path.join(__dirname, '..', 'lib', 'consent.ts'), 'utf8');
    const { outputText } = ts.transpileModule(src, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    });
    const mod = { exports: {} as Record<string, unknown> };
    new Function('module', 'exports', outputText)(mod, mod.exports);
    return mod.exports as unknown as ConsentModule;
  };
  // consent.ts не залежить від React: підставляємо мінімальний window з localStorage.
  const setup = (raw: string | null) => {
    const store = new Map<string, string>();
    if (raw !== null) store.set('cookie_consent', raw);
    (globalThis as unknown as { window: unknown }).window = {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
        removeItem: (k: string) => void store.delete(k),
      },
      dispatchEvent: () => true,
      addEventListener: () => {},
      removeEventListener: () => {},
    };
  };
  const json = (level: string, version: string | null) => JSON.stringify({ level, version, ts: null });

  test('"all" діє, коли версія та сама або повторна згода не потрібна', () => {
    const c = loadConsent();
    setup(json('all', 'v1'));
    c.registerLegalVersion('v2', false);
    expect(c.hasAnalyticsConsent()).toBe(true);
    c.registerLegalVersion('v1', true);
    expect(c.hasAnalyticsConsent()).toBe(true);
    setup('all'); // старе значення без версії
    c.registerLegalVersion('', true);
    expect(c.hasAnalyticsConsent()).toBe(true);
  });

  test('"all" не діє, коли версія змінилась і потрібна повторна згода', () => {
    const c = loadConsent();
    setup(json('all', 'v1'));
    c.registerLegalVersion('v2', true);
    expect(c.hasAnalyticsConsent()).toBe(false);
    setup('all'); // без версії теж питаємо знову
    c.registerLegalVersion('v2', true);
    expect(c.hasAnalyticsConsent()).toBe(false);
  });

  test('"necessary", порожнє й пошкоджене значення: false', () => {
    const c = loadConsent();
    c.registerLegalVersion('v1', false);
    for (const raw of [json('necessary', 'v1'), null, '{broken']) {
      setup(raw);
      expect(c.hasAnalyticsConsent()).toBe(false);
    }
  });
});
