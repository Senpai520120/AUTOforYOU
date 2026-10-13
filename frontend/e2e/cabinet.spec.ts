/**
 * E2E: сторінки кабінету на даних e2e_seed (23-P5).
 */
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

test.describe('Кабінет seller', () => {
  test.use({ storageState: storageStatePath('seller') });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  test('/me/local-listings: активне і pending-оголошення [E2E]', async ({ page }) => {
    await page.goto('/me/local-listings');
    await expect(page.getByRole('heading', { name: 'Мої оголошення' })).toBeVisible();

    const active = page.getByRole('link', { name: 'Skoda Octavia 2018' });
    const pending = page.getByRole('link', { name: 'Toyota Camry 2018' });
    await expect(active).toBeVisible();
    await expect(pending).toBeVisible();

    // Статус перевіряємо в межах картки конкретного оголошення, а не по сторінці загалом.
    const activeCard = page.locator('div.rounded-xl').filter({ has: active });
    const pendingCard = page.locator('div.rounded-xl').filter({ has: pending });
    await expect(activeCard.getByText('Активне', { exact: true })).toBeVisible();
    await expect(pendingCard.getByText('На модерації', { exact: true })).toBeVisible();
    await expect(pendingCard.getByText('Очікує перевірки модератором')).toBeVisible();
  });
});

test.describe('Кабінет buyer', () => {
  test.use({ storageState: storageStatePath('buyer') });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  test('/me/messages: діалог із seller відкривається і показує повідомлення', async ({ page }) => {
    await page.goto('/me/messages');
    const conv = page.getByRole('button', { name: /seller/ });
    await expect(conv).toBeVisible();
    await conv.click();

    await expect(page.getByRole('link', { name: 'Переглянути оголошення →' })).toBeVisible();
    // Текст є і в списку діалогів, і в треді; тред — останній.
    await expect(page.getByText('[E2E] Здравствуйте!').last()).toBeVisible();
  });

  test('/me/shipments: контейнер [E2E]', async ({ page }) => {
    await page.goto('/me/shipments');
    await expect(page.getByRole('heading', { name: 'Мої контейнери' })).toBeVisible();
    await expect(page.getByText('E2E-0000001')).toBeVisible();
  });

  for (const [path, heading] of [
    ['/me/favorites', 'Обране'],
    ['/me/deals', 'Мої угоди'],
    ['/me/notifications', 'Сповіщення'],
  ] as const) {
    test(`${path} відкривається без помилок консолі`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));

      await page.goto(path);
      await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible();
      // Завантаження даних закінчене, коли зник індикатор.
      await expect(page.getByText(/^Завантаження/)).toHaveCount(0);

      expect(errors, `pageerror: ${errors.join(' | ')}`).toEqual([]);
    });
  }

  test.fixme('08-Q6 → задача 6.2: помилка API /favorites показується, а не порожній стан', async ({ page }) => {
    await page.route('**/api/v1/favorites/**', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"boom"}' }),
    );
    await page.goto('/me/favorites');
    await expect(page.getByRole('heading', { name: 'Обране', level: 1 })).toBeVisible();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByText('Тут будуть збережені оголошення.')).toHaveCount(0);
  });
});
