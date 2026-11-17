/**
 * E2E: юридичні сторінки та підвал показують реквізити з налаштувань сайту (задача 1.12).
 * Налаштування виставляє `manage.py e2e_seed` (E2E_SITE_SETTINGS).
 */
import { test, expect } from './fixtures';

const PAGES = ['/privacy', '/terms', '/refund', '/rules', '/cookies'] as const;

test.describe('Юридичні сторінки з реквізитами', () => {
  for (const path of PAGES) {
    test(`${path}: реквізити, email, дата; плашки «Шаблон» немає`, async ({ page }) => {
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(200);
      const main = page.locator('main');

      await expect(main.getByText('[E2E] Тестовий Власник').first()).toBeVisible();
      await expect(main.getByText('1234567890').first()).toBeVisible();
      await expect(main.getByText('Останнє оновлення: 01.10.2026')).toBeVisible();
      await expect(page.getByText('Шаблон — потребує перевірки юристом')).toHaveCount(0);
      await expect(main.getByText('Реквізити власника ще не заповнені')).toHaveCount(0);
      await expect(main.getByText(/заповнити|вписати|\[X\]/)).toHaveCount(0);
    });
  }

  test('privacy: email для звернень, /me/data, омбудсман, партнер без вигадок', async ({ page }) => {
    await page.goto('/privacy');
    const main = page.locator('main');

    await expect(main.getByRole('link', { name: 'privacy@e2e.test' })).toBeVisible();
    await expect(main.getByRole('link', { name: 'Мої дані' })).toHaveAttribute('href', '/me/data');
    await expect(main.getByText('Уповноваженого Верховної Ради України з прав людини')).toBeVisible();
    // partner_name задано в сіді (потрібен для заявок, задача 2.3): показується саме воно.
    await expect(page.getByTestId('privacy-partner')).toContainText('[E2E] Партнер');
    await expect(main.getByText(/переглянуті оголошення/i)).toHaveCount(0);
    await expect(main.getByText('Ім\'я й телефон клієнта в цю групу не передаються')).toBeVisible();
  });

  test('terms: контактний email', async ({ page }) => {
    await page.goto('/terms');
    await expect(page.locator('main').getByRole('link', { name: 'support@e2e.test' })).toBeVisible();
  });

  test('підвал: реквізити, контакти, Telegram, 5 посилань і дисклеймер партнера', async ({ page }) => {
    await page.goto('/terms');
    const footer = page.locator('footer');

    const requisites = footer.getByTestId('footer-requisites');
    await expect(requisites).toContainText('[E2E] Тестовий Власник');
    await expect(requisites).toContainText('1234567890');
    await expect(requisites).toContainText('support@e2e.test');
    await expect(requisites).toContainText('+380500000000');
    await expect(requisites.getByRole('link', { name: 'Telegram' })).toHaveAttribute(
      'href',
      'https://t.me/e2e_channel',
    );
    for (const href of ['/terms', '/rules', '/refund', '/privacy', '/cookies']) {
      await expect(footer.locator(`a[href="${href}"]`)).toHaveCount(1);
    }
    await expect(footer.getByText('Послугу пригону надає партнер, а не AUTOforYOU')).toBeVisible();
  });

  // Порожні налаштування: у e2e-сіді вони заповнені, а змінити їх з браузера немає як
  // (серверний fetch Next не перехоплюється page.route; адмін-API для налаштувань немає).
  // Порожній стан покриває Django-тест site_settings/tests.py і ручна перевірка.
  test.fixme('порожні налаштування: «Реквізити власника ще не заповнені адміністратором» і плашка «Шаблон» → 1.12 (потрібен e2e-перемикач налаштувань)', async () => {});
});
