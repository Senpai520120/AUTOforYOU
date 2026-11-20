/**
 * E2E 10.24: каталог /ua на мобільному — згорнуті фільтри зі лічильником, «≈ $» на картці,
 * порожній результат зі скиданням і посиланням на калькулятор.
 */
import { test, expect } from './fixtures';

type Flags = { c2c_enabled: boolean };
let flags: Flags;

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  const res = await ctx.get('/api/v1/site-settings/');
  expect(res.status()).toBe(200);
  flags = await res.json();
  await ctx.dispose();
});

test.describe('Каталог /ua на мобільному @mobile', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!flags.c2c_enabled, 'C2C вимкнено (E2E_C2C=off)');
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
    await page.setViewportSize({ width: 375, height: 812 });
  });

  test('фільтри згорнуті, лічильник після застосування, розкриття працює', async ({ page }) => {
    await page.goto('/ua');
    const toggle = page.getByRole('button', { name: 'Фільтри', exact: true });
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByLabel('Марка', { exact: true })).toBeHidden();

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await page.getByLabel('Марка', { exact: true }).fill('Renault');
    await page.getByRole('button', { name: 'Застосувати' }).click();

    await expect(page).toHaveURL(/make=Renault/);
    await expect(page.getByRole('button', { name: 'Фільтри (1)' })).toHaveAttribute('aria-expanded', 'false');
  });

  test('картка оголошення в UAH показує «≈ $»', async ({ page }) => {
    await page.goto('/ua?make=Renault&model=Duster');
    const card = page.locator('article').filter({ hasText: 'Renault Duster' }).first();
    await expect(card).toBeVisible();
    await expect(card).toContainText('UAH');
    await expect(card.getByText(/≈ \$/)).toBeVisible();
  });

  test('порожній результат: кнопка скидання і посилання на калькулятор', async ({ page }) => {
    await page.goto('/ua?make=ZzNoSuchMake');
    await expect(page.getByText('Оголошень не знайдено')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Порахувати пригон з США' })).toHaveAttribute('href', '/calculator');
    await page.getByRole('link', { name: 'Скинути фільтри' }).click();
    await expect(page).toHaveURL(/\/ua$/);
  });
});
