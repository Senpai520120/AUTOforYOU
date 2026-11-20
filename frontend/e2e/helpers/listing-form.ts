/**
 * Хелпери форми оголошення частника і мобільного каталогу (10.23, 10.24).
 */
import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

/** Підтверджений номер seller з e2e_seed (users/management/commands/e2e_seed.py, verified_phone). */
export const SELLER_VERIFIED_PHONE = '+380670000001';

/** contact_phone сид-оголошень (e2e_seed, `_local_listings`). */
export const SEED_LISTING_PHONE = '+380671112233';

/**
 * 10.23: у користувача з підтвердженим телефоном поле «Контактний телефон» лише для читання
 * (номер підставляє сервер) — заповнюємо тільки якщо воно редаговане.
 */
export async function fillContactPhone(page: Page, phone: string) {
  const field = page.getByLabel('Контактний телефон');
  await expect(field).toBeVisible();
  if (await field.isEditable()) await field.fill(phone);
}

/** 10.24: на вузькому екрані фільтри каталогу згорнуті за кнопкою «Фільтри (N)»; на десктопі кнопка прихована. */
export async function openMobileFilters(page: Page) {
  const toggle = page.getByRole('button', { name: /^Фільтри/ });
  if (await toggle.isVisible() && (await toggle.getAttribute('aria-expanded')) === 'false') {
    // Клік до гідратації React губиться — повторюємо, поки панель не розкриється.
    await expect(async () => {
      if ((await toggle.getAttribute('aria-expanded')) === 'false') await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', 'true', { timeout: 1000 });
    }).toPass();
  }
}
