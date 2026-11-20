/**
 * E2E: реєстрація — обов'язкова згода з Умовами та Політикою конфіденційності.
 */
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

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

  test('без згоди форма не відправляється', async ({ page }, testInfo) => {
    await page.goto('/register');

    // Унікальний email: інакше після першого прогону «зайнятий email» теж лишає на /register.
    await page.fill('input[type="email"]', `e2e-consent-${Date.now()}-${testInfo.workerIndex}@e2e.test`);
    await page.locator('input[type="password"]').first().fill('StrongPass123!');
    await page.locator('input[type="password"]').nth(1).fill('StrongPass123!');

    await page.getByLabel(/18 років/).check();
    const consent = page.getByLabel(/Погоджуюсь з/);
    const isRegisterPost = (r: { url(): string; method(): string }) =>
      r.url().includes('/auth/register/') && r.method() === 'POST';
    const submit = page.getByRole('button', { name: 'Зареєструватися' });
    const pageError = page.getByText(/Необхідно погодитися з Умовами/);

    // Захист 1: браузерний required. Сабміт заблокований, запиту немає.
    await expectNoRequest(page, isRegisterPost, async () => {
      await submit.click();
    });
    expect(await consent.evaluate((el: HTMLInputElement) => el.validity.valueMissing)).toBe(true);
    await expect(page).toHaveURL(/\/register/);
    await expect(pageError).toHaveCount(0);

    // Захист 2: перевірка на самій сторінці. Знімаємо required — браузер пропускає
    // сабміт, але сторінка має показати помилку й не слати запит.
    await consent.evaluate((el: HTMLInputElement) => el.removeAttribute('required'));
    await expectNoRequest(page, isRegisterPost, async () => {
      await submit.click();
      await expect(pageError).toBeVisible();
    });
    await expect(page).toHaveURL(/\/register/);
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

test.describe('Реєстрація: помилки сервера біля полів (10.28)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
  });

  test('email зайнятий (400 по полю) → текст біля email, aria-invalid, фокус на полі', async ({ page, uniqueEmail }) => {
    const message = 'Користувач з таким email вже існує.';
    await page.route('**/api/v1/auth/register/', route =>
      route.fulfill({ status: 400, json: { email: [message] } }));

    await page.goto('/register');
    const email = page.getByLabel('Email');
    await email.fill(uniqueEmail);
    await page.locator('input[type="password"]').first().fill('StrongPass123!');
    await page.locator('input[type="password"]').nth(1).fill('StrongPass123!');
    await page.getByLabel(/Погоджуюсь з/).check();
    await page.getByLabel(/18 років/).check();
    await page.getByRole('button', { name: 'Зареєструватися' }).click();

    await expect(page.getByText(message)).toBeVisible();
    await expect(email).toHaveAttribute('aria-invalid', 'true');
    await expect(email).toHaveAccessibleDescription(message);
    await expect(email).toBeFocused();
  });

  test('autocomplete, inputmode і шрифт 16px у полях реєстрації та входу', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByLabel("Ім'я")).toHaveAttribute('autocomplete', 'given-name');
    await expect(page.getByLabel('Email')).toHaveAttribute('autocomplete', 'email');
    await expect(page.getByLabel('Телефон')).toHaveAttribute('autocomplete', 'tel');
    await expect(page.getByLabel('Телефон')).toHaveAttribute('inputmode', 'tel');
    await expect(page.getByLabel('Пароль', { exact: true })).toHaveAttribute('autocomplete', 'new-password');
    const size = await page.getByLabel('Email').evaluate(el => parseFloat(getComputedStyle(el).fontSize));
    expect(size).toBeGreaterThanOrEqual(16);

    await page.goto('/login');
    await expect(page.getByLabel('Пароль', { exact: true })).toHaveAttribute('autocomplete', 'current-password');
  });
});
