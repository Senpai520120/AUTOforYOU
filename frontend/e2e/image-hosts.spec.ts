/**
 * E2E: оптимізатор зображень Next приймає лише дозволені хости (задача 7.2, 08-C8, 08-S10).
 *
 * Дозволені: медіа бекенду (хост NEXT_PUBLIC_API_URL, шлях /media/) і хости з NEXT_PUBLIC_IMAGE_HOSTS.
 * Широких шаблонів (*.cloudfront.net, *.amazonaws.com) і хостів аукціонів за замовчуванням немає.
 */
import { test, expect } from './fixtures';

test.use({ storageState: { cookies: [], origins: [] } });

const optimizer = (url: string) => `/_next/image?url=${encodeURIComponent(url)}&w=640&q=75`;

test.describe('next/image: білий список хостів', () => {
  test('успіх: фото оголошення з медіа бекенду віддається через /_next/image', async ({ request }) => {
    // У e2e-стеку медіа на http://localhost, а Next 16 забороняє оптимізатору локальні IP
    // ("url" parameter is not allowed) незалежно від білого списку. Перевірити на стенді з доменом/R2.
    test.fixme(true, '7.2-image-ok → 7.5 (стенд з доменом або R2)');
    const resp = await request.get('/api/v1/local/listings/');
    expect(resp.status()).toBe(200);
    const body = (await resp.json()) as { results: { images: { image: string | null }[] }[] };
    const image = body.results.flatMap((l) => l.images).find((i) => i.image)?.image;
    expect(image, 'e2e_seed створює оголошення з фото').toBeTruthy();
    const img = await request.get(optimizer(image!));
    expect(img.status()).toBe(200);
    expect(img.headers()['content-type']).toMatch(/^image\//);
  });

  test('обхід: довільний хост, *.cloudfront.net, *.copart.com і amazonaws → 400', async ({ request }) => {
    for (const url of [
      'https://evil.example.com/x.jpg',
      'https://d1234.cloudfront.net/x.jpg',
      'https://cs.copart.com/v1/x.jpg',
      'https://bucket.s3.eu-central-1.amazonaws.com/x.jpg',
    ]) {
      const resp = await request.get(optimizer(url));
      expect(resp.status(), url).toBe(400);
    }
  });
});
