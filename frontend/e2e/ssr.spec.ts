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

test.describe('Серверний рендер каталогів @smoke', () => {
  test.use({ javaScriptEnabled: false });

  test('каталог України віддає вміст без JavaScript', async ({ page }) => {
    const resp = await page.goto('/ua');
    expect(resp?.status()).toBe(200);

    await expect(page.getByRole('heading', { name: 'Каталог Україна' })).toBeVisible();
    // Або картки з лічильником, або порожній стан — але не скелетон.
    await expect(page.getByText(/Знайдено:|Оголошень не знайдено/)).toBeVisible();
    await expect(page.locator('.animate-pulse')).toHaveCount(0);
  });

  test.fixme('2.8 → модуль заморожено до 2.9/2.10/2.11/3.3: каталог імпорту віддає вміст без JavaScript', async ({ page }) => {
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
    // Точні елементи <loc>, а не підрядок (13-Q16): '/ua' як підрядок збігся б з будь-яким '/ua…'.
    const paths = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => new URL(m[1]).pathname);
    // /ua - єдиний розділ з реальними оголошеннями.
    expect(paths).toContain('/ua');
    // /listings заморожен флагом (2.8): в sitemap его нет.
    expect(paths.filter((p) => p.startsWith('/listings'))).toEqual([]);
    expect(paths).toContain('/refund');
  });
});
