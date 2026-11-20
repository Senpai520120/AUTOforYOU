/**
 * E2E: обробка фото оголошень (задача 8.4).
 * Стек e2e: C2C_ENABLED=true, подача відкрита, LOCAL_LISTING_MIN_PHOTOS=1 (за замовчуванням),
 * розміри — із налаштувань за замовчуванням. Дані — e2e_seed: active «[E2E] Skoda Octavia (active)» продавця seller з 1 фото.
 * Дія «Схвалити» в адмінці без фото перевіряється Django-тестом (local_listings/tests_photos.py).
 */
import fs from 'fs';
import path from 'path';
import type { APIRequestContext } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';
import { expectNoRequest } from './helpers/network';
import { fillContactPhone } from './helpers/listing-form';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const LARGE = path.join(__dirname, 'fixtures', 'large-dimensions.jpg');

type Img = { id: number; image: string | null; thumbnail: string | null };

async function seeded(api: (r: 'seller') => Promise<APIRequestContext>) {
  const seller = await api('seller');
  const body = await (await seller.get('/api/v1/local/my-listings/')).json();
  const items: { id: number; description: string }[] = Array.isArray(body) ? body : body.results;
  const found = items.find((l) => l.description.startsWith('[E2E] Skoda Octavia (active)'));
  if (!found) throw new Error('e2e_seed: немає active-оголошення');
  return { seller, id: found.id };
}

test.describe('Фото: ресайз і мініатюри (8.4)', () => {
  test.use({ storageState: storageStatePath('seller') });
  test.beforeEach(async ({ page }) => { await page.addInitScript(consentInit); });

  test('успіх: великий JPEG зменшено, мініатюра менша за оригінал', async ({ page, api }) => {
    const { seller, id } = await seeded(api);
    const config = await (await seller.get('/api/v1/local/config/')).json();
    const resp = await seller.post(`/api/v1/local/listings/${id}/images/`, {
      multipart: { images: { name: 'big.jpg', mimeType: 'image/jpeg', buffer: fs.readFileSync(LARGE) } },
    });
    expect(resp.status()).toBe(201);
    const [img] = (await resp.json()) as Img[];
    try {
      expect(img.thumbnail).toMatch(/\/media\/local_listings\/thumbs\/[0-9a-f]{32}\.jpg$/);
      await page.goto('/ua'); // відносні шляхи /media/… — від адреси стенду
      const sizes = await page.evaluate(async ([full, thumb]) => {
        const load = (src: string) => new Promise<[number, number]>((ok, fail) => {
          const el = new Image();
          el.onload = () => ok([el.naturalWidth, el.naturalHeight]);
          el.onerror = fail;
          el.src = src;
        });
        return { full: await load(full), thumb: await load(thumb) };
      }, [new URL(img.image!, 'http://localhost').pathname, new URL(img.thumbnail!, 'http://localhost').pathname]);
      expect(Math.max(...sizes.full)).toBeLessThan(3000); // оригінал 3000×2000 зменшено
      expect(Math.max(...sizes.thumb)).toBeLessThan(Math.max(...sizes.full));
      expect(config.min_photos).toBe(1);
    } finally {
      expect((await seller.delete(`/api/v1/local/listings/${id}/images/${img.id}/`)).status()).toBe(204);
    }
  });

  test('обхід: видалити останнє фото через API → 400 з причиною', async ({ api }) => {
    const { seller, id } = await seeded(api);
    const detail = await (await seller.get(`/api/v1/local/my-listings/${id}/`)).json();
    expect(detail.photos_count).toBe(1);
    const resp = await seller.delete(`/api/v1/local/listings/${id}/images/${detail.images[0].id}/`);
    expect(resp.status()).toBe(400);
    expect((await resp.json()).detail).toBe('Не можна видалити: потрібно щонайменше 1 фото.');
  });

  test('обхід: нове оголошення без фото — «Додайте щонайменше 1 фото», запит створення не йде', async ({ page }) => {
    await page.goto('/local/new');
    await page.getByLabel('Марка').fill('Skoda');
    await page.getByLabel('Модель').fill('[E2E] Без фото');
    await page.getByLabel('Рік').fill('2016');
    await page.getByLabel('Пробіг, км').fill('150000');
    await page.getByLabel('Ціна').fill('7000');
    await page.getByRole('combobox', { name: 'Населений пункт *' }).fill('Вінниц');
    await page.getByRole('option', { name: /^Вінниця/ }).click();
    await page.getByLabel('Опис').fill('[E2E] без фото');
    await fillContactPhone(page, '+380501112297');
    // 8.5: дві відмітки — правила і «не в розшуку, не в заставі»
    await page.getByRole('checkbox', { name: /правилами/ }).check();
    await page.getByRole('checkbox', { name: /не в розшуку/ }).check();
    await expectNoRequest(
      page, (r) => r.url().endsWith('/api/v1/local/listings/') && r.method() === 'POST',
      async () => { await page.getByRole('button', { name: 'Надіслати на модерацію' }).click(); },
    );
    await expect(page.getByText('Додайте щонайменше 1 фото').first()).toBeVisible();
  });

  test('кабінет: у оголошення без фото — жовта плашка «Додайте щонайменше 1 фото»', async ({ page, api }) => {
    const { seller } = await seeded(api);
    const cities = await (await seller.get('/api/v1/local/cities/?q=вінниц')).json();
    const created = await seller.post('/api/v1/local/listings/', {
      data: {
        make: 'Skoda', model: '[E2E] Плашка', year: 2014, mileage_km: 1, price: '1000', currency: 'USD',
        fuel_type: 'petrol', transmission: 'manual', body_type: 'sedan', condition: 'used',
        region: cities[0].region, city: cities[0].id, description: '[E2E] плашка', contact_phone: '+380501112296',
        agreed_to_rules: true, legal_confirmed: true,
      },
    });
    expect(created.status()).toBe(201);
    const listingId = (await created.json()).id;
    await page.goto('/me/local-listings');
    const card = page.locator('li, article, div').filter({ hasText: '[E2E] Плашка' }).filter({
      has: page.getByRole('status').filter({ hasText: 'Додайте щонайменше 1 фото' }),
    }).last();
    await expect(card).toBeVisible();
    await expect(card.getByRole('link', { name: 'Додати фото' })).toHaveAttribute('href', `/local/${listingId}/edit`);
  });
});
