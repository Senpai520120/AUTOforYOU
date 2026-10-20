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
    await page.getByLabel(/18 років/).check();

    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    await expect(page).toHaveURL(/\/register/);
    expect(await email.evaluate((el: HTMLInputElement) => el.validity.typeMismatch)).toBe(true);
  });

  test('паролі, що не збігаються, відхиляються сервером', async ({ page }) => {
    await page.locator('input[type="email"]').fill(uniqueEmail());
    await page.locator('input[type="password"]').first().fill('StrongPass123!');
    await page.locator('input[type="password"]').nth(1).fill('OtherPass456!');
    await page.getByLabel(/Погоджуюсь з/).check();
    await page.getByLabel(/18 років/).check();

    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    await expect(page.getByText(/Паролі не збігаються/)).toBeVisible();
    await expect(page).toHaveURL(/\/register/);
  });

  test('повторна реєстрація на той самий email не розкриває, що адреса зайнята (01-S11)', async ({ page }) => {
    const email = uniqueEmail();

    const submit = async () => {
      await page.locator('input[type="email"]').fill(email);
      await page.locator('input[type="password"]').first().fill('StrongPass123!');
      await page.locator('input[type="password"]').nth(1).fill('StrongPass123!');
      await page.getByLabel(/Погоджуюсь з/).check();
      await page.getByLabel(/18 років/).check();
      await page.getByRole('button', { name: 'Зареєструватися' }).click();
    };

    const [first] = await Promise.all([waitRegisterResponse(page), submit()]);
    expect(first.status()).toBe(201);
    await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();

    await page.goto('/register');
    const [second] = await Promise.all([waitRegisterResponse(page), submit()]);

    // Той самий 201 і той самий екран, що й для нового email; тексту про «зайнятий» немає.
    expect(second.status()).toBe(201);
    expect(await second.json()).toEqual(await first.json());
    await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();
    await expect(page.getByText(/already exists|вже існує|зайнят/i)).toHaveCount(0);
  });

  test('надто простий пароль відхиляється валідатором Django', async ({ page }) => {
    await page.locator('input[type="email"]').fill(uniqueEmail());
    await page.locator('input[type="password"]').first().fill('12345678');
    await page.locator('input[type="password"]').nth(1).fill('12345678');
    await page.getByLabel(/Погоджуюсь з/).check();
    await page.getByLabel(/18 років/).check();

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

  const RESULT = 'Деталізація вартості «під ключ»';
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

    // Ціна: значення зберігається як рядок, тож порожнє поле лишається порожнім.
    const price = page.getByLabel(fields[0], { exact: true });
    expect(await price.evaluate((e: HTMLInputElement) => e.validity.valueMissing), fields[0]).toBe(true);

    // ЗНАХІДКА (сторінку тут не чіпаємо): engine_cc і vehicle_year пишуться як
    // Number(e.target.value), тож порожнє поле миттєво стає «0» і required
    // ніколи не спрацьовує. Фіксуємо фактичний стан: рік 0 блокується min=1990,
    // а об'єм 0 проходить min=0 (валідним вважається).
    test.info().annotations.push({
      type: 'finding',
      description: 'calculator: порожні engine_cc/vehicle_year коерсяться в 0, required не спрацьовує',
    });
    const engine = page.getByLabel(fields[1], { exact: true });
    const year = page.getByLabel(fields[2], { exact: true });
    await expect(engine).toHaveValue('0');
    await expect(year).toHaveValue('0');
    expect(await year.evaluate((e: HTMLInputElement) => e.validity.rangeUnderflow)).toBe(true);
  });
});
