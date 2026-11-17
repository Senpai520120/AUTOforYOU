/**
 * E2E: головна сторінка.
 *
 * Блок «Свіжі авто» прибрано разом із заморозкою каталогу лотів (задача 2.8).
 */
import { test, expect } from '@playwright/test';

test.describe('Головна сторінка @smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('cookie_consent', 'necessary');
    });
    await page.goto('/');
  });

  test('hero веде в калькулятор', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Авто з США під ключ в Україну' })).toBeVisible();

    const calc = page.getByRole('link', { name: 'Порахувати вартість' });
    await expect(calc).toBeVisible();
    await calc.click();
    await expect(page).toHaveURL(/\/calculator$/);
  });

  test('блок «Два напрямки» розводить імпорт і локальний каталог', async ({ page }) => {
    const section = page.getByRole('region', { name: 'Два напрямки' });
    await expect(section).toBeVisible();

    // Каталог лотів заморожено (2.8): картка імпорту веде в калькулятор.
    await expect(section.getByRole('link', { name: /Імпорт з аукціонів США/ })).toHaveAttribute(
      'href',
      '/calculator',
    );
    await expect(section.getByRole('link', { name: /Каталог Україна/ })).toHaveAttribute('href', '/ua');
  });

  test('«Як це працює» містить чотири етапи по порядку', async ({ page }) => {
    const steps = page.getByRole('region', { name: 'Як це працює' }).getByRole('listitem');
    await expect(steps).toHaveCount(4);

    await expect(steps.nth(0)).toContainText('Обираєте лот');
    await expect(steps.nth(1)).toContainText('Рахуєте вартість');
    await expect(steps.nth(2)).toContainText('Викуп і доставка');
    await expect(steps.nth(3)).toContainText('Розмитнення');
  });

  test('блок вартості перелічує статті і веде в калькулятор', async ({ page }) => {
    const section = page.getByRole('region', { name: 'Що входить у розрахунок' });
    await expect(section).toBeVisible();

    // Ключові статті названі без цифр ставок і портів (6.4, 08-C3): цифри — тільки в калькуляторі.
    await expect(section).toContainText('Мито та ПДВ');
    await expect(section).not.toContainText('10%');
    await expect(section).not.toContainText('20%');
    await expect(section).toContainText('Пенсійний збір');

    await section.getByRole('link', { name: 'Відкрити калькулятор' }).click();
    await expect(page).toHaveURL(/\/calculator$/);
  });

  test('футер описує обидва напрямки, а не тільки США', async ({ page }) => {
    const footer = page.getByRole('contentinfo');
    await expect(footer).toContainText('Оголошення по Україні');
    // Раніше тут стояло «маркетплейс авто з США» — і на сторінці локальних
    // оголошень це виглядало як чужий футер.
    await expect(footer).not.toContainText('маркетплейс авто з США');
  });
});
