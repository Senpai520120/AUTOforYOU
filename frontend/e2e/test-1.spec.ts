/**
 * E2E: навігація в шапці сайту.
 *
 * Файл народився як чернетка codegen: перший рядок був
 * `page.goto('chrome-error://chromewebdata/')` — codegen записав сторінку
 * помилки Chrome, бо стартував з недоступної адреси. Ассерти при цьому
 * знімалися з робочої головної, тому їх варто було зберегти.
 *
 * Що прибрано з чернетки:
 *  - три картки-фічі («Каталог авто», «Калькулятор», «Трекінг») — їх більше
 *    немає, головна перероблена на «Два напрямки»;
 *  - старі тексти футера — переписані;
 *  - дублі ассертів, згенеровані повторними кліками під час запису.
 *
 * Залишилося те, чого не покриває жоден інший спек: шапка.
 */
import { test, expect } from '@playwright/test';

test.describe('Шапка сайту', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('cookie_consent', 'necessary');
    });
    await page.goto('/');
  });

  test('логотип веде на головну', async ({ page }) => {
    await page.goto('/calculator');
    await page.getByRole('banner').getByRole('link', { name: /AUTO\s*forYOU/ }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test('навігація веде на три основні розділи', async ({ page }) => {
    const nav = page.getByRole('banner');

    await expect(nav.getByRole('link', { name: 'Пригін/аукціон' })).toHaveAttribute('href', '/listings');
    await expect(nav.getByRole('link', { name: 'Каталог Україна' })).toHaveAttribute('href', '/ua');
    await expect(nav.getByRole('link', { name: 'Калькулятор' })).toHaveAttribute('href', '/calculator');
  });

  test('гостю показані вхід і реєстрація', async ({ page }) => {
    const header = page.getByRole('banner');
    await expect(header.getByRole('link', { name: 'Увійти' })).toHaveAttribute('href', '/login');
    await expect(header.getByRole('link', { name: 'Реєстрація' })).toHaveAttribute('href', '/register');
  });

  test('гостю не показані розділи кабінету', async ({ page }) => {
    const header = page.getByRole('banner');
    await expect(header.getByRole('link', { name: 'Сповіщення' })).toHaveCount(0);
    await expect(header.getByRole('link', { name: 'Повідомлення' })).toHaveCount(0);
    await expect(header.getByRole('button', { name: 'Вийти' })).toHaveCount(0);
  });

  test('перехід у каталог України через шапку', async ({ page }) => {
    await page.getByRole('banner').getByRole('link', { name: 'Каталог Україна' }).click();
    await expect(page).toHaveURL(/\/ua$/);
    await expect(page.getByRole('heading', { name: 'Каталог Україна' })).toBeVisible();
  });
});
