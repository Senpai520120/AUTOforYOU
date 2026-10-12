/**
 * E2E: негативні сценарії.
 *
 * Перевіряють, що форма НЕ пропускає некоректний ввід. Кожен тест
 * підтверджує не тільки відсутність результату, а й причину відмови:
 * інакше тест був би зеленим і тоді, коли форма зламалася зовсім і не
 * відправляється взагалі.
 */
import { test, expect, type Page } from '@playwright/test';
import { expectNoRequest } from './helpers/network';

const CONSENT = () => {
  window.localStorage.setItem('cookie_consent', 'necessary');
};

/** Унікальний email — реєстрація пише в БД, повтори між прогонами не потрібні. */
const uniqueEmail = () => `e2e-neg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@e2e.test`;

const waitRegisterResponse = (page: Page) =>
  page.waitForResponse(r => r.url().includes('/auth/register/') && r.request().method() === 'POST');

/** Той самий склад повідомлення, що збирає сторінка: усі тексти помилок через '. '. */
const serverErrorText = (data: Record<string, string[] | string>, field: string): string => {
  expect(Object.keys(data), 'відповідь API має містити помилку цього поля').toContain(field);
  const text = Object.values(data).flat().join('. ');
  expect(text.length).toBeGreaterThan(0);
  return text;
};

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
    const [resp] = await Promise.all([waitRegisterResponse(page), submit()]);

    expect(resp.status()).toBe(400);
    // Текст беремо з відповіді API (поле email), а не з CSS-класу чи англійської фрази.
    const expected = serverErrorText(await resp.json(), 'email');
    await expect(page).toHaveURL(/\/register/);
    await expect(page.getByText(expected, { exact: true })).toBeVisible();
  });

  test('надто простий пароль відхиляється валідатором Django', async ({ page }) => {
    await page.locator('input[type="email"]').fill(uniqueEmail());
    await page.locator('input[type="password"]').first().fill('12345678');
    await page.locator('input[type="password"]').nth(1).fill('12345678');
    await page.getByLabel(/Погоджуюсь з/).check();

    const [resp] = await Promise.all([
      waitRegisterResponse(page),
      page.getByRole('button', { name: 'Зареєструватися' }).click(),
    ]);

    expect(resp.status()).toBe(400);
    const expected = serverErrorText(await resp.json(), 'password');
    await expect(page).toHaveURL(/\/register/);
    await expect(page.getByText(expected, { exact: true })).toBeVisible();
  });
});

test.describe('Калькулятор — негативні сценарії', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(CONSENT);
    await page.goto('/calculator');
  });

  const RESULT = 'Детализация стоимости «под ключ»';
  const isCalcPost = (r: { url(): string; method(): string }) =>
    r.url().includes('/pricing/calculate/') && r.method() === 'POST';

  /** Клік «Розрахувати»: запиту до API не має бути (вікно очікування), результату теж. */
  const submitExpectNoCalc = async (page: Page) => {
    await expectNoRequest(page, isCalcPost, async () => {
      await page.getByRole('button', { name: 'Розрахувати' }).click();
    });
    await expect(page.getByRole('heading', { name: RESULT })).toHaveCount(0);
  };

  test('відʼємна ціна не проходить', async ({ page }) => {
    const price = page.getByLabel('Ціна аукціону ($)', { exact: true });
    await price.fill('-5000');
    await submitExpectNoCalc(page);
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

    await submitExpectNoCalc(page);
    expect(await price.evaluate((el: HTMLInputElement) => el.validity.valueMissing)).toBe(true);
  });

  test('обʼєм двигуна понад ліміт не проходить', async ({ page }) => {
    const engine = page.getByLabel("Об'єм двигуна (см³)", { exact: true });
    await engine.fill('99999');
    await submitExpectNoCalc(page);
    expect(await engine.evaluate((el: HTMLInputElement) => el.validity.rangeOverflow)).toBe(true);
  });

  test('рік випуску раніше 1990 не проходить', async ({ page }) => {
    const year = page.getByLabel('Рік випуску', { exact: true });
    await year.fill('1200');
    await submitExpectNoCalc(page);
    expect(await year.evaluate((el: HTMLInputElement) => el.validity.rangeUnderflow)).toBe(true);
  });

  test('порожня форма не відправляється', async ({ page }) => {
    const fields = ['Ціна аукціону ($)', "Об'єм двигуна (см³)", 'Рік випуску'];
    for (const label of fields) {
      await page.getByLabel(label, { exact: true }).fill('');
    }
    await submitExpectNoCalc(page);
    for (const label of fields) {
      const el = page.getByLabel(label, { exact: true });
      expect(await el.evaluate((e: HTMLInputElement) => e.validity.valueMissing), label).toBe(true);
    }
  });
});
