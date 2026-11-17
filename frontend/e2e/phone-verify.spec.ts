/**
 * E2E: подача оголошення лише з підтвердженим телефоном (задача 4.10).
 * Стек e2e: C2C_ENABLED=true, подача відкрита, PHONE_VERIFICATION_REQUIRED=true (за замовчуванням).
 * Бот на e2e-стеку не налаштований: видачу посилання і профіль після «перевірити» підміняє page.route;
 * справжній шлях через бота (свій/чужий контакт) перевіряють Django-тести telegram_bot/tests_phone.py.
 * dealer — без підтвердженого телефону (не staff, тож крок показується), seller — з підтвердженим (e2e_seed).
 */
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

test.describe('Підтвердження телефону (4.10)', () => {
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test.describe('без підтвердження', () => {
    test.use({ storageState: storageStatePath('dealer') });

    test('форма подачі закрита кроком «Підтвердіть телефон»; після підтвердження форма відкривається', async ({ page }) => {
      let verified = false;
      await page.route('**/api/v1/telegram/link-token/', (route) => route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ configured: true, link: 'https://t.me/afy_test_bot?start=link_x', bot_username: 'afy_test_bot' }),
      }));
      await page.route('**/api/v1/auth/profile/', async (route) => {
        if (route.request().method() !== 'GET' || !verified) return route.continue();
        const resp = await route.fetch();
        const body = await resp.json();
        return route.fulfill({ response: resp, json: { ...body, phone_verified: true, verified_phone: '+380670000099' } });
      });

      await page.goto('/local/new');
      await expect(page.getByRole('heading', { name: 'Підтвердіть телефон' })).toBeVisible();
      await expect(page.getByLabel('Марка')).toHaveCount(0);
      await page.getByRole('button', { name: 'Підтвердити через Telegram' }).click();
      await expect(page.getByRole('link', { name: 'Відкрити бота в Telegram' }))
        .toHaveAttribute('href', /^https:\/\/t\.me\/.+\?start=/);

      verified = true; // «бот прийняв власний контакт»
      await page.getByRole('button', { name: /Я поділився контактом/ }).click();
      await expect(page.getByLabel('Марка')).toBeVisible();
    });

    test('обхід: без підтвердження «перевірити» лишає крок, а прямий POST → 403 phone_not_verified', async ({ page, api }) => {
      await page.route('**/api/v1/telegram/link-token/', (route) => route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ configured: true, link: 'https://t.me/afy_test_bot?start=link_x', bot_username: 'afy_test_bot' }),
      }));
      await page.goto('/local/new');
      await page.getByRole('button', { name: 'Підтвердити через Telegram' }).click();
      await page.getByRole('button', { name: /Я поділився контактом/ }).click();
      await expect(page.getByRole('status').filter({ hasText: 'Телефон ще не підтверджено' })).toBeVisible();
      await expect(page.getByLabel('Марка')).toHaveCount(0);

      const dealer = await api('dealer');
      const cities = await (await dealer.get('/api/v1/local/cities/?q=вінниц')).json();
      const resp = await dealer.post('/api/v1/local/listings/', {
        data: {
          make: 'Skoda', model: '[E2E] Без телефону', year: 2015, mileage_km: 1, price: '1000', currency: 'USD',
          fuel_type: 'petrol', transmission: 'manual', body_type: 'sedan', condition: 'used',
          region: cities[0].region, city: cities[0].id, description: '[E2E]', contact_phone: '+380501112295',
          agreed_to_rules: true, legal_confirmed: true,
        },
      });
      expect(resp.status()).toBe(403);
      expect((await resp.json()).code).toBe('phone_not_verified');
    });

    test('кабінет Telegram показує «Телефон не підтверджено»', async ({ page }) => {
      await page.goto('/me/telegram');
      await expect(page.getByTestId('phone-status')).toContainText('Телефон не підтверджено');
    });
  });

  test.describe('з підтвердженням', () => {
    test.use({ storageState: storageStatePath('seller') });

    test('продавець з підтвердженим телефоном одразу бачить форму і статус у кабінеті', async ({ page }) => {
      await page.goto('/local/new');
      await expect(page.getByLabel('Марка')).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Підтвердіть телефон' })).toHaveCount(0);
      await page.goto('/me/telegram');
      await expect(page.getByTestId('phone-status')).toContainText('Телефон підтверджено');
    });
  });
});
