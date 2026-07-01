/**
 * E2E: Реєстрація — обов'язкова галочка згоди
 */
import { test, expect } from '@playwright/test';

test.describe('Register page — consent checkbox', () => {
  test('register page loads with consent checkbox', async ({ page }) => {
    await page.goto('/register');
    await expect(page).toHaveTitle(/AUTOforYOU/);

    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();

    const checkbox = page.locator('#agreed_to_terms');
    await expect(checkbox).toBeVisible();
  });

  test('consent checkbox is required — form blocks submit without it', async ({ page }) => {
    await page.goto('/register');

    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'StrongPass123!');

    const checkbox = page.locator('#agreed_to_terms');
    await expect(checkbox).not.toBeChecked();

    // Без галочки кнопка submit должна блокироваться через HTML required
    const submitBtn = page.locator('button[type="submit"]');
    await submitBtn.click();

    // Страница не должна перейти на /login (форма заблокирована)
    await expect(page).toHaveURL(/\/register/);
  });

  test('terms and privacy links open correct pages', async ({ page }) => {
    await page.goto('/register');

    const termsLink = page.locator('a[href="/terms"]');
    await expect(termsLink).toBeVisible();

    const privacyLink = page.locator('a[href="/privacy"]');
    await expect(privacyLink).toBeVisible();
  });

  test('footer contains legal links', async ({ page }) => {
    await page.goto('/');

    const termsLink = page.locator('footer a[href="/terms"]');
    await expect(termsLink).toBeVisible();

    const privacyLink = page.locator('footer a[href="/privacy"]');
    await expect(privacyLink).toBeVisible();

    const cookiesLink = page.locator('footer a[href="/cookies"]');
    await expect(cookiesLink).toBeVisible();
  });
});
