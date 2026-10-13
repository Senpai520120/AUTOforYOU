/**
 * E2E: банер згоди на cookie (23-P7). Банер тут НЕ придушується.
 */
import { test, expect } from './fixtures';

test.use({ storageState: { cookies: [], origins: [] } });

const BANNER = 'Налаштування файлів cookie';

test.describe('Банер cookie (23-P7)', () => {
  test('перший візит: банер видно', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
  });

  for (const [button, stored, label] of [
    ['Лише необхідні', 'necessary', 'Лише необхідні'],
    ['Прийняти всі', 'all', 'Прийняті всі'],
  ] as const) {
    test(`«${button}» ховає банер і запам'ятовується (${stored})`, async ({ page }) => {
      await page.goto('/');
      const banner = page.getByRole('dialog', { name: BANNER });
      await banner.getByRole('button', { name: button }).click();
      await expect(banner).toBeHidden();
      expect(await page.evaluate(() => localStorage.getItem('cookie_consent'))).toBe(stored);

      await page.reload();
      // Банер не рендериться до гідратації, тому «банера немає» одразу після reload
      // нічого не доводить. Спершу дочікуємось гідратованого стану на /cookies.
      await page.goto('/cookies');
      await expect(page.locator('strong', { hasText: label })).toBeVisible();
      await expect(page.getByRole('dialog', { name: BANNER })).toHaveCount(0);
      expect(await page.evaluate(() => localStorage.getItem('cookie_consent'))).toBe(stored);
    });
  }

  test('/cookies: поточний вибір відображається і змінюється', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('dialog', { name: BANNER }).getByRole('button', { name: 'Лише необхідні' }).click();

    await page.goto('/cookies');
    await expect(page.locator('strong', { hasText: 'Лише необхідні' })).toBeVisible();

    await page.getByRole('button', { name: 'Прийняти всі' }).click();
    await expect(page.locator('strong', { hasText: 'Прийняті всі' })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('cookie_consent'))).toBe('all');
  });

  test('/cookies: «Відкликати згоду» повертає банер і скидає вибір', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('dialog', { name: BANNER }).getByRole('button', { name: 'Прийняти всі' }).click();

    await page.goto('/cookies');
    await expect(page.locator('strong', { hasText: 'Прийняті всі' })).toBeVisible();
    await page.getByRole('button', { name: 'Відкликати згоду' }).click();

    await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
    await expect(page.locator('strong', { hasText: 'ще не зроблено' })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('cookie_consent'))).toBeNull();
  });

  test('до згоди немає запитів до сторонніх доменів (крім зображень)', async ({ page, baseURL }) => {
    const siteHost = new URL(baseURL!).hostname;
    const isThirdParty = (r: { url(): string; resourceType(): string }) => {
      if (r.resourceType() === 'image') return false;
      const u = new URL(r.url());
      if (u.protocol === 'data:' || u.protocol === 'blob:') return false;
      // Порівнюємо хост без порту: API може стояти на іншому порту того ж хоста.
      return u.hostname !== siteHost;
    };

    const hits: string[] = [];
    page.on('request', (r) => {
      if (isThirdParty(r)) hits.push(`${r.resourceType()} ${r.url()}`);
    });

    for (const path of ['/', '/listings', '/calculator']) {
      await page.goto(path);
      await expect(page.getByRole('dialog', { name: BANNER })).toBeVisible();
    }
    expect(await page.evaluate(() => localStorage.getItem('cookie_consent'))).toBeNull();
    expect(hits, `Сторонні запити до згоди: ${hits.join(', ')}`).toEqual([]);
  });
});
