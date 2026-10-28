/**
 * Smoke после деплоя (задача 7.5, 23-P54): только чтение, без логина и без записи данных.
 * Против боевого сайта: E2E_BASE_URL=https://<домен> E2E_ALLOW_REMOTE=1 npx playwright test --project=smoke
 *
 * Состояние ВОЛНЫ-1 (заморожены лоты, B2B, дилеры, контейнеры): /listings, /b2b и /api/calculate/ дают 404.
 * Раздел «Оголошення по Україні» зависит от флага C2C_ENABLED: режим читается из GET /api/v1/site-settings/.
 *
 * Сценарии с тегом @backend-down выполняются только при E2E_BACKEND_STOPPED=1 (CI останавливает backend командой
 * `docker compose stop backend`): `E2E_BACKEND_STOPPED=1 npx playwright test --project=smoke --grep @backend-down`.
 */
import { test, expect } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const SOON = 'Оголошення по Україні — незабаром';
const BACKEND_STOPPED = process.env.E2E_BACKEND_STOPPED === '1';

test.use({ storageState: { cookies: [], origins: [] } });

test.describe('Smoke: публичные страницы @smoke', () => {
  test.skip(BACKEND_STOPPED, 'backend остановлен намеренно: работает только @backend-down');

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  for (const path of ['/', '/calculator', '/how-it-works', '/privacy', '/terms']) {
    test(`${path} → 200 @smoke`, async ({ page }) => {
      const resp = await page.goto(path, { waitUntil: 'domcontentloaded' });
      expect(resp?.status()).toBe(200);
    });
  }

  test('/healthz → 200 @smoke', async ({ request }) => {
    expect((await request.get('/healthz')).status()).toBe(200);
  });

  test('у главной есть <title> @smoke', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveTitle(/AUTOforYOU/);
  });
});

test.describe('Smoke: замороженные модули дают 404 @smoke', () => {
  test.skip(BACKEND_STOPPED, 'backend остановлен намеренно: работает только @backend-down');

  for (const path of ['/listings', '/b2b']) {
    test(`${path} → 404 @smoke`, async ({ page }) => {
      await page.addInitScript(consentInit);
      const resp = await page.goto(path, { waitUntil: 'domcontentloaded' });
      expect(resp?.status()).toBe(404);
    });
  }

  test('/api/calculate/ → 404 @smoke', async ({ request }) => {
    expect((await request.get('/api/calculate/')).status()).toBe(404);
  });
});

test.describe('Smoke: раздел «Оголошення по Україні» по флагу C2C_ENABLED @smoke', () => {
  test.skip(BACKEND_STOPPED, 'backend остановлен намеренно: работает только @backend-down');

  test('каталог и /ua соответствуют флагу из site-settings @smoke', async ({ page, request }) => {
    const settings = await request.get('/api/v1/site-settings/');
    expect(settings.status()).toBe(200);
    const { c2c_enabled: c2cEnabled } = (await settings.json()) as { c2c_enabled: boolean };
    expect(typeof c2cEnabled).toBe('boolean');

    const catalog = await request.get('/api/v1/local/listings/');
    await page.addInitScript(consentInit);
    const resp = await page.goto('/ua', { waitUntil: 'domcontentloaded' });
    if (c2cEnabled) {
      expect(catalog.status()).toBe(200);
      expect(resp?.status()).toBe(200);
      await expect(page.getByRole('heading', { name: SOON })).toHaveCount(0);
    } else {
      expect(catalog.status()).toBe(404);
      await expect(page.getByRole('heading', { name: SOON })).toBeVisible();
    }
  });
});

// backend остановлен: nginx отдаёт JSON 503 для /api/, фронтенд живёт. Главная рендерится без API (serverGet возвращает
// null, блоки показывают запасной текст), калькулятор грузит тарифы в браузере и показывает свою ошибку.
// Сырой 502/503 страницы nginx в обоих случаях быть не должно.
test.describe('Smoke: backend остановлен @backend-down', () => {
  test.skip(!BACKEND_STOPPED, 'нужен E2E_BACKEND_STOPPED=1 (в CI после `docker compose stop backend`)');

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  test('главная: оформленная страница, не сырая ошибка nginx @backend-down', async ({ page }) => {
    const resp = await page.goto('/', { waitUntil: 'domcontentloaded' });
    expect(resp?.status()).toBe(200);
    await expect(page).toHaveTitle(/AUTOforYOU/);
    await expect(page.getByRole('link', { name: 'Порахувати вартість' })).toBeVisible();
    await expect(page.locator('body')).not.toContainText(/Bad Gateway|Service Unavailable|nginx/i);
  });

  test('/calculator: оформленное сообщение об ошибке загрузки @backend-down', async ({ page }) => {
    // Первый запрос nginx к остановленному backend ждёт proxy_connect_timeout (замер локально: ~38 с), потом 503.
    test.setTimeout(120_000);
    const resp = await page.goto('/calculator', { waitUntil: 'domcontentloaded' });
    expect(resp?.status()).toBe(200);
    await expect(page.getByRole('alert').filter({ hasText: 'Не вдалося завантажити калькулятор' })).toBeVisible({ timeout: 90_000 });
    await expect(page.locator('body')).not.toContainText(/Bad Gateway|Service Unavailable|nginx/i);
  });
});
