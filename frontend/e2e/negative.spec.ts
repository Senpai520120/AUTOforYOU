/**
 * E2E: негативні сценарії.
 *
 * Перевіряють, що форма НЕ пропускає некоректний ввід. Кожен тест
 * підтверджує не тільки відсутність результату, а й причину відмови:
 * інакше тест був би зеленим і тоді, коли форма зламалася зовсім і не
 * відправляється взагалі.
 */
import { test, expect } from '@playwright/test';

const CONSENT = () => {
  window.localStorage.setItem('cookie_consent', 'necessary');
};

/** Унікальний email — реєстрація пише в БД, повтори між прогонами не потрібні. */
const uniqueEmail = () => `e2e-neg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;

test.describe('Реєстрація — негативні сценарії', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(CONSENT);
    await page.goto('/register');
  });

  test('невалідний email блокується браузером', async ({ page }) => {
    const email = page.locator('input[type="email"]');
    await email.fill('не-email');
    await page.locator('input[type="password"]').first().fill('StrongPass123!');
    await page.locator('input[type="password"]').nth(1).fill('StrongPass123!');
    await page.getByLabel(/Погоджуюсь з/).check();

    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    await expect(page).toHaveURL(/\/register/);
    expect(await email.evaluate((el: HTMLInputElement) => el.validity.typeMismatch)).toBe(true);
  });

  test('паролі, що не збігаються, відхиляються сервером', async ({ page }) => {
    await page.locator('input[type="email"]').fill(uniqueEmail());
    await page.locator('input[type="password"]').first().fill('StrongPass123!');
    await page.locator('input[type="password"]').nth(1).fill('OtherPass456!');
    await page.getByLabel(/Погоджуюсь з/).check();

    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    await expect(page.getByText(/Паролі не збігаються/)).toBeVisible();
    await expect(page).toHaveURL(/\/register/);
  });

  test('повторна реєстрація на той самий email відхиляється', async ({ page }) => {
    const email = uniqueEmail();

    const submit = async () => {
      await page.locator('input[type="email"]').fill(email);
      await page.locator('input[type="password"]').first().fill('StrongPass123!');
      await page.locator('input[type="password"]').nth(1).fill('StrongPass123!');
      await page.getByLabel(/Погоджуюсь з/).check();
      await page.getByRole('button', { name: 'Зареєструватися' }).click();
    };

    await submit();
    await expect(page).toHaveURL(/\/login/);

    await page.goto('/register');
    await submit();

    await expect(page).toHaveURL(/\/register/);
    await expect(page.locator('.text-red-600')).toBeVisible();
  });

  test('надто простий пароль відхиляється валідатором Django', async ({ page }) => {
    await page.locator('input[type="email"]').fill(uniqueEmail());
    await page.locator('input[type="password"]').first().fill('12345678');
    await page.locator('input[type="password"]').nth(1).fill('12345678');
    await page.getByLabel(/Погоджуюсь з/).check();

    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    await expect(page).toHaveURL(/\/register/);
    await expect(page.locator('.text-red-600')).toBeVisible();
  });
});

test.describe('Калькулятор — негативні сценарії', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(CONSENT);
    await page.goto('/calculator');
  });

  const RESULT = 'Детализация стоимости «под ключ»';

  test('відʼємна ціна не проходить', async ({ page }) => {
    const price = page.getByLabel('Ціна аукціону ($)', { exact: true });
    await price.fill('-5000');
    await page.getByRole('button', { name: 'Розрахувати' }).click();

    await expect(page.getByRole('heading', { name: RESULT })).toHaveCount(0);
    // Причина саме в min=0, а не в тому, що форма взагалі не працює.
    expect(await price.evaluate((el: HTMLInputElement) => el.validity.rangeUnderflow)).toBe(true);
  });

  test('нечислова ціна не потрапляє в поле', async ({ page }) => {
    const price = page.getByLabel('Ціна аукціону ($)', { exact: true });
    await price.fill('');
    // Саме друк з клавіатури, а не fill(): fill() на input[type=number]
    // кидає виняток на нечисловому значенні й тест впав би з помилки
    // Playwright, а не через поведінку сторінки.
    await price.click();
    await page.keyboard.type('десять тисяч');

    // input[type=number] не приймає літери — поле лишається порожнім.
    await expect(price).toHaveValue('');

    await page.getByRole('button', { name: 'Розрахувати' }).click();
    await expect(page.getByRole('heading', { name: RESULT })).toHaveCount(0);
    expect(await price.evaluate((el: HTMLInputElement) => el.validity.valueMissing)).toBe(true);
  });

  test('обʼєм двигуна понад ліміт не проходить', async ({ page }) => {
    const engine = page.getByLabel("Об'єм двигуна (см³)", { exact: true });
    await engine.fill('99999');
    await page.getByRole('button', { name: 'Розрахувати' }).click();

    await expect(page.getByRole('heading', { name: RESULT })).toHaveCount(0);
    expect(await engine.evaluate((el: HTMLInputElement) => el.validity.rangeOverflow)).toBe(true);
  });

  test('рік випуску раніше 1990 не проходить', async ({ page }) => {
    const year = page.getByLabel('Рік випуску', { exact: true });
    await year.fill('1200');
    await page.getByRole('button', { name: 'Розрахувати' }).click();

    await expect(page.getByRole('heading', { name: RESULT })).toHaveCount(0);
    expect(await year.evaluate((el: HTMLInputElement) => el.validity.rangeUnderflow)).toBe(true);
  });

  test('порожня форма не відправляється', async ({ page }) => {
    for (const label of ['Ціна аукціону ($)', "Об'єм двигуна (см³)", 'Рік випуску']) {
      await page.getByLabel(label, { exact: true }).fill('');
    }
    await page.getByRole('button', { name: 'Розрахувати' }).click();

    await expect(page.getByRole('heading', { name: RESULT })).toHaveCount(0);
  });
});
