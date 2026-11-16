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
    // У /ua немає loading.tsx навмисно: з ним Next спершу віддає скелетон, а каталог стримить у <div hidden>,
    // і без JS (у т.ч. Bingbot/Twitterbot) видно лише скелетон.
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

test.describe('Фото оголошень у серверному HTML (10.3) @smoke', () => {
  test('адреса фото публічна, без внутрішнього хоста бекенду', async ({ request }) => {
    const html = await (await request.get('/ua')).text();
    // e2e_seed кладе фото в оголошення: без цього перевірка нижче пройшла б порожньою.
    expect(html).toContain('%2Fmedia%2F');
    // Сервер Next ходить в API через http://backend:8000; ця адреса не має потрапити в HTML.
    expect(html).not.toContain('backend:8000');
    expect(html).not.toContain('backend%3A8000');
  });

  test('фото, що не завантажилось, не зациклює запити', async ({ page }) => {
    let imageRequests = 0;
    page.on('request', (req) => {
      if (req.url().includes('/_next/image')) imageRequests += 1;
    });
    await page.goto('/ua');
    const cards = await page.locator('article img').count();
    expect(cards).toBeGreaterThan(0);
    // Цикл (заміна src в onError, яку React скидає) дає десятки запитів за секунди.
    await page.waitForTimeout(3000);
    expect(imageRequests).toBeLessThanOrEqual(cards * 2);
  });
});
