/**
 * E2E: реєстрація — обов'язкова згода з Умовами та Політикою конфіденційності.
 */
import { test, expect } from '@playwright/test';

test.describe("Реєстрація — згода з умовами", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('cookie_consent', 'necessary');
    });
  });

  test('форма містить поля і чекбокс згоди', async ({ page }) => {
    await page.goto('/register');
    await expect(page).toHaveTitle(/AUTOforYOU/);

    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.getByLabel(/Погоджуюсь з/)).toBeVisible();
    await expect(page.getByLabel(/Погоджуюсь з/)).not.toBeChecked();
  });

  test('без згоди форма не відправляється', async ({ page }) => {
    await page.goto('/register');

    await page.fill('input[type="email"]', 'e2e-consent@example.com');
    await page.locator('input[type="password"]').first().fill('StrongPass123!');
    await page.locator('input[type="password"]').nth(1).fill('StrongPass123!');

    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    // Чекбокс має required — браузер блокує відправку, URL не змінюється.
    await expect(page).toHaveURL(/\/register/);
    await expect(page.getByLabel(/Погоджуюсь з/)).not.toBeChecked();
  });

  test('посилання «Умовами використання» відкриває сторінку умов', async ({ page, context }) => {
    await page.goto('/register');

    // Раніше тест називався «open correct pages», але нікуди не переходив —
    // перевіряв лише видимість. До того ж локатор a[href="/terms"] збігався
    // з двома елементами (текст згоди і футер) і падав на strict mode.
    const [popup] = await Promise.all([
      context.waitForEvent('page'),
      page.getByRole('link', { name: 'Умовами використання' }).click(),
    ]);

    await popup.waitForLoadState();
    await expect(popup).toHaveURL(/\/terms$/);
    await expect(popup.getByRole('heading', { name: 'Умови використання' })).toBeVisible();
  });

  test('посилання «Політикою конфіденційності» відкриває сторінку політики', async ({ page, context }) => {
    await page.goto('/register');

    const [popup] = await Promise.all([
      context.waitForEvent('page'),
      page.getByRole('link', { name: 'Політикою конфіденційності' }).click(),
    ]);

    await popup.waitForLoadState();
    await expect(popup).toHaveURL(/\/privacy$/);
    await expect(popup.getByRole('heading', { name: 'Політика конфіденційності' })).toBeVisible();
  });

  test('футер містить посилання на юридичні документи', async ({ page }) => {
    await page.goto('/');

    const footer = page.getByRole('contentinfo');
    await expect(footer.getByRole('link', { name: 'Умови використання' })).toBeVisible();
    await expect(footer.getByRole('link', { name: 'Правила розміщення' })).toBeVisible();
    await expect(footer.getByRole('link', { name: 'Конфіденційність' })).toBeVisible();
    await expect(footer.getByRole('link', { name: 'Cookie' })).toBeVisible();
  });
});
