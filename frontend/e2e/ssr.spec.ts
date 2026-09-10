/**
 * E2E: каталоги мають рендеритись на сервері.
 *
 * Перевірка з вимкненим JavaScript — це рівно те, що бачить пошуковий робот
 * без виконання скриптів. Раніше обидва каталоги вантажили дані в useEffect:
 * у HTML приходив скелетон, і жодного оголошення робот не бачив, хоча
 * sitemap.ts обіцяв йому ці сторінки.
 *
 * Скелетон позначений класом animate-pulse — його наявність без JS і означала б
 * повернення до клієнтського завантаження.
 */
import { test, expect } from '@playwright/test';

test.describe('Серверний рендер каталогів', () => {
  test.use({ javaScriptEnabled: false });

  test('каталог України віддає вміст без JavaScript', async ({ page }) => {
    const resp = await page.goto('/ua');
    expect(resp?.status()).toBe(200);

    await expect(page.getByRole('heading', { name: 'Каталог Україна' })).toBeVisible();
    // Або картки з лічильником, або порожній стан — але не скелетон.
    await expect(page.getByText(/Знайдено:|Оголошень не знайдено/)).toBeVisible();
    await expect(page.locator('.animate-pulse')).toHaveCount(0);
  });

  test('каталог імпорту віддає вміст без JavaScript', async ({ page }) => {
    const resp = await page.goto('/listings');
    expect(resp?.status()).toBe(200);

    await expect(page.getByRole('heading', { name: 'Каталог автомобілів' })).toBeVisible();
    await expect(page.getByText(/Знайдено:|Оголошень не знайдено/)).toBeVisible();
    await expect(page.locator('.animate-pulse')).toHaveCount(0);
  });

  test('головна віддає блоки без JavaScript', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Авто з США під ключ в Україну' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Як це працює' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Що входить у розрахунок' })).toBeVisible();
  });

  test('sitemap містить каталог України', async ({ request }) => {
    const resp = await request.get('/sitemap.xml');
    expect(resp.status()).toBe(200);

    const xml = await resp.text();
    // /ua раніше в sitemap не потрапляв, хоча це єдиний розділ з реальними
    // оголошеннями.
    expect(xml).toContain('/ua');
    expect(xml).toContain('/listings');
    expect(xml).toContain('/refund');
  });
});
