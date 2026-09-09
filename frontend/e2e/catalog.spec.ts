/**
 * E2E: каталог імпорту з США та калькулятор вартості «під ключ».
 *
 * Запуск:
 *   docker compose up -d          (з кореня репозиторію)
 *   cd frontend && npx playwright test
 */
import { test, expect } from '@playwright/test';

// Текст заголовка демо-банера. Навмисно не збігається з текстом у футері
// («Тестові тарифи — всі розрахунки є демонстраційними»), інакше перевірка
// відсутності банера ловила б футер і завжди була б хибною.
const DEMO_BANNER = 'Тестові тарифи — розрахунок демонстраційний';

test.describe('Каталог імпорту з США', () => {
  test('сторінка каталогу відповідає 200 і рендерить заголовок', async ({ page }) => {
    const resp = await page.goto('/listings');
    expect(resp?.status()).toBe(200);
    await expect(page).toHaveTitle(/AUTOforYOU/);
    await expect(page.getByRole('heading', { name: 'Каталог автомобілів' })).toBeVisible();
  });

  test('демо-банер на каталозі не показується', async ({ page }) => {
    // DemoBanner рендериться тільки на /calculator і всередині CalcBreakdown.
    // Раніше цей тест називався «demo banner is visible on catalog page»,
    // оголошував локатор банера і не перевіряв його — був зеленим завжди.
    await page.goto('/listings');
    await expect(page.getByText(DEMO_BANNER)).toHaveCount(0);
  });
});

test.describe('Калькулятор вартості', () => {
  test.beforeEach(async ({ page }) => {
    // Знімаємо банер згоди: він fixed bottom з z-50 і може перекривати кнопку
    // відправки. Вибір робиться до завантаження сторінки, банер не з'явиться.
    await page.addInitScript(() => {
      window.localStorage.setItem('cookie_consent', 'necessary');
    });
  });

  test('форма містить підписані поля і демо-банер', async ({ page }) => {
    await page.goto('/calculator');
    await expect(page).toHaveTitle(/AUTOforYOU/);

    await expect(page.getByLabel('Ціна аукціону ($)', { exact: true })).toBeVisible();
    await expect(page.getByLabel("Об'єм двигуна (см³)", { exact: true })).toBeVisible();
    await expect(page.getByLabel('Рік випуску', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Тип палива', { exact: true })).toBeVisible();

    await expect(page.getByText(DEMO_BANNER).first()).toBeVisible();
  });

  test('розрахунок повертає повну деталізацію вартості', async ({ page }) => {
    await page.goto('/calculator');

    await page.getByLabel('Ціна аукціону ($)', { exact: true }).fill('5000');
    await page.getByLabel("Об'єм двигуна (см³)", { exact: true }).fill('2000');
    await page.getByLabel('Рік випуску', { exact: true }).fill('2018');
    await page.getByRole('button', { name: 'Розрахувати' }).click();

    // Раніше тут стояв if (count > 0) навколо кліку і waitForTimeout(3000):
    // тест був зеленим навіть якщо кнопки не існує, а розрахунок не відбувся.
    await expect(
      page.getByRole('heading', { name: 'Детализация стоимости «под ключ»' }),
    ).toBeVisible();

    for (const article of [
      'Цена аукциона',
      'Аукционный сбор',
      'Логистика США',
      'Морской фрахт',
      'Пошлина 10%',
      'НДС 20%',
      'Пенсионный сбор',
    ]) {
      await expect(page.getByRole('cell', { name: article, exact: true })).toBeVisible();
    }

    // Підсумок має бути додатним числом, а не прочерком.
    const total = page.getByRole('row').filter({ hasText: 'ИТОГО' });
    await expect(total).toBeVisible();
    await expect(total).not.toContainText('—');
  });
});

test.describe('Обробка помилок', () => {
  test('невідомий маршрут повертає 404 і сторінку не знайдено', async ({ page }) => {
    const resp = await page.goto('/this-page-does-not-exist-xyz');
    expect(resp?.status()).toBe(404);
    await expect(page.getByRole('heading', { name: 'Сторінку не знайдено' })).toBeVisible();
  });
});
