/**
 * E2E: безпечне завантаження фото (задача 1.10).
 *
 * - Успіх: продавець завантажує JPEG з GPS у своє оголошення; фото з'являється, файл
 *   віддається з uuid-іменем, `nosniff` і без EXIF.
 * - Обхід: HTML, перейменований у .jpg, і файл понад ліміт — видима помилка, фото не додається;
 *   фото трекінгу без авторизації недоступне ні через API, ні напряму з /media/.
 */
import fs from 'fs';
import path from 'path';
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const GPS_PHOTO = path.join(__dirname, 'fixtures', 'car-gps.jpg');
const EXIF_MARKER = Buffer.from('Exif\0\0', 'binary');
// Ліміт за замовчуванням — 8 МБ (UPLOAD_IMAGE_MAX_SIZE_MB; .env.e2e його не змінює).
const OVER_LIMIT_BYTES = 9 * 1024 * 1024;

type Img = { id: number; image: string | null };
type Listing = { id: number; make: string; model: string; images?: Img[] };

test.describe('Фото оголошення: продавець', () => {
  test.use({ storageState: storageStatePath('seller') });

  let listingId: number;
  let initialIds: number[];

  test.beforeEach(async ({ page, api }) => {
    await page.addInitScript(consentInit);
    const seller = await api('seller');
    const mine = await seller.get('/api/v1/local/my-listings/');
    expect(mine.status()).toBe(200);
    const results: Listing[] = (await mine.json()).results;
    const listing = results.find((l) => l.make === 'Skoda' && l.model === 'Octavia');
    expect(listing, 'e2e_seed: оголошення Skoda Octavia продавця').toBeTruthy();
    listingId = listing!.id;
    const detail = await seller.get(`/api/v1/local/listings/${listingId}/`);
    expect(detail.status()).toBe(200);
    initialIds = ((await detail.json()).images as Img[]).map((i) => i.id);
  });

  test.afterEach(async ({ api }) => {
    // Прибираємо все, що додав тест: інші спеки бачать оголошення з одним фото з сиду.
    const seller = await api('seller');
    const detail = await seller.get(`/api/v1/local/listings/${listingId}/`);
    const images: Img[] = (await detail.json()).images;
    for (const img of images.filter((i) => !initialIds.includes(i.id))) {
      const res = await seller.delete(`/api/v1/local/listings/${listingId}/images/${img.id}/`);
      expect(res.status()).toBe(204);
    }
  });

  const counter = (n: number) => `Фото (${n}/15)`;

  test('JPEG з GPS: фото з’являється, файл без EXIF, uuid-ім’я, nosniff', async ({ page }) => {
    const source = fs.readFileSync(GPS_PHOTO);
    expect(source.includes(EXIF_MARKER), 'фікстура має EXIF з GPS').toBe(true);

    await page.goto(`/local/${listingId}/edit`);
    await expect(page.getByText(counter(initialIds.length))).toBeVisible();

    const uploaded = page.waitForResponse(
      (r) => r.url().endsWith(`/listings/${listingId}/images/`) && r.request().method() === 'POST',
    );
    await page.locator('input[type="file"]').setInputFiles({
      name: 'my-home-gps.jpg', mimeType: 'image/jpeg', buffer: source,
    });
    const response = await uploaded;
    expect(response.status()).toBe(201);
    const [created] = (await response.json()) as Img[];

    await expect(page.getByText(counter(initialIds.length + 1))).toBeVisible();

    // Сериалізатор може віддати відносний шлях /media/… — база: адреса стенду.
    const url = new URL(created.image!, page.url());
    expect(url.pathname).toMatch(/^\/media\/local_listings\/[0-9a-f]{32}\.jpg$/);
    expect(url.pathname).not.toContain('my-home');

    const file = await page.request.get(url.pathname);
    expect(file.status()).toBe(200);
    expect(file.headers()['x-content-type-options']).toBe('nosniff');
    expect(file.headers()['content-type']).toBe('image/jpeg');
    expect((await file.body()).includes(EXIF_MARKER)).toBe(false);
  });

  test('HTML під виглядом .jpg і файл понад ліміт — помилка, фото не додається', async ({ page }) => {
    await page.goto(`/local/${listingId}/edit`);
    await expect(page.getByText(counter(initialIds.length))).toBeVisible();
    const input = page.locator('input[type="file"]');

    const rejectedHtml = page.waitForResponse(
      (r) => r.url().endsWith(`/listings/${listingId}/images/`) && r.request().method() === 'POST',
    );
    await input.setInputFiles({
      name: 'evil.jpg', mimeType: 'image/jpeg',
      buffer: Buffer.from('<html><body><script>alert(document.cookie)</script></body></html>'),
    });
    expect((await rejectedHtml).status()).toBe(400);
    await expect(page.getByText(/evil\.jpg: Файл не є зображенням/)).toBeVisible();

    const rejectedBig = page.waitForResponse(
      (r) => r.url().endsWith(`/listings/${listingId}/images/`) && r.request().method() === 'POST',
    );
    const big = Buffer.concat([fs.readFileSync(GPS_PHOTO), Buffer.alloc(OVER_LIMIT_BYTES)]);
    await input.setInputFiles({ name: 'huge.jpg', mimeType: 'image/jpeg', buffer: big });
    expect((await rejectedBig).status()).toBe(400);
    await expect(page.getByText(/huge\.jpg: Файл завеликий/)).toBeVisible();

    await expect(page.getByText(counter(initialIds.length))).toBeVisible();
  });
});

test.describe('Фото трекінгу: приватна віддача', () => {
  test.fixme('2.8 → модуль заморожено до 2.9/2.10/2.11/3.3: watcher отримує фото; аноніму 401; прямі шляхи до файлу — 404 від nginx', async ({ request, api }) => {
    // e2e_seed: контейнер покупця (buyer — watcher) з подією, у якої є фото.
    const buyer = await api('buyer');
    const list = await buyer.get('/api/v1/shipments/');
    expect(list.status()).toBe(200);
    const [shipment] = (await list.json()).results as { id: number }[];
    expect(shipment, 'e2e_seed: контейнер покупця').toBeTruthy();
    const detail = await buyer.get(`/api/v1/shipments/${shipment.id}/`);
    expect(detail.status()).toBe(200);
    const body = await detail.text();
    expect(body).not.toContain('/media/');
    const events = JSON.parse(body).events as { photo: string | null }[];
    const photoUrl = events.find((e) => e.photo)?.photo;
    expect(photoUrl, 'e2e_seed: подія з фото').toMatch(/^\/api\/v1\/shipments\/\d+\/events\/\d+\/photo\/$/);

    // Watcher: Django перевіряє права, файл віддає nginx через X-Accel-Redirect.
    const own = await buyer.get(photoUrl!);
    expect(own.status()).toBe(200);
    expect(own.headers()['content-type']).toBe('image/jpeg');
    expect(own.headers()['x-accel-redirect']).toBeUndefined();
    const disposition = own.headers()['content-disposition'] ?? '';
    const fileName = disposition.match(/filename="([0-9a-f]{32}\.jpg)"/)?.[1];
    expect(fileName, `ім'я файлу з Content-Disposition: ${disposition}`).toBeTruthy();
    expect((await own.body()).subarray(0, 2).toString('hex')).toBe('ffd8');

    const anon = await request.get(photoUrl!);
    expect(anon.status()).toBe(401);

    for (const direct of [`/media/tracking_photos/${fileName}`, `/protected-media/tracking_photos/${fileName}`]) {
      const res = await request.get(direct);
      expect(res.status(), direct).toBe(404);
      // Відповідь саме nginx, а не сторінка 404 від Next.
      expect(res.headers()['x-powered-by'], direct).toBeUndefined();
      expect(await res.text(), direct).toContain('<center>nginx</center>');
    }
  });
});
