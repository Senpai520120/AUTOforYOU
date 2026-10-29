import { expect, test } from './fixtures';

/**
 * Заголовки безпеки nginx (задача 7.1, 12-S3, 01-S9, C7).
 * HTTP-стенд (TLS_MODE=off): усі перевірки, крім TLS. TLS-стенд (TLS_MODE=selfsigned) запускається
 * з E2E_TLS_STAND=1 і E2E_BASE_URL=https://localhost, проєкт `tls` у playwright.config.ts.
 */
const TLS_STAND = process.env.E2E_TLS_STAND === '1';

// /me для гостя - редирект 307 от proxy.ts: заголовки nginx должны быть и на нём.
const PAGES: Array<[string, number]> = [['/', 200], ['/login', 200], ['/me', 307], ['/calculator', 200]];

for (const [path, expectedStatus] of PAGES) {
  test(`7.1 сторінка ${path}: CSP, X-Frame-Options, nosniff, Referrer-Policy`, async ({ request }) => {
    const res = await request.get(path, { maxRedirects: 0 });
    expect(res.status()).toBe(expectedStatus);
    const h = res.headers();
    expect(h['content-security-policy']).toContain("frame-ancestors 'none'");
    expect(h['content-security-policy']).toContain("object-src 'none'");
    expect(h['x-frame-options']).toBe('DENY');
    expect(h['x-content-type-options']).toBe('nosniff');
    expect(h['referrer-policy']).toBe('strict-origin-when-cross-origin');
    expect(h['permissions-policy']).toContain('camera=()');
    expect(h['server']).not.toMatch(/\d/); // server_tokens off: без номера версії
  });
}

test('7.1 /password-reset зберігає Referrer-Policy: no-referrer від Next (1.7)', async ({ request }) => {
  const res = await request.get('/password-reset/confirm', { maxRedirects: 0 });
  expect(res.headers()['referrer-policy']).toBe('no-referrer');
});

test('7.1 /api, /static і /media теж з nosniff, без дублів заголовків', async ({ request }) => {
  const api = await request.get('/api/v1/auth/csrf/');
  expect(api.headers()['x-content-type-options']).toBe('nosniff');
  expect(api.headers()['x-frame-options']).toBe('DENY');

  const media = await request.get('/media/e2e-no-such-file.jpg');
  expect(media.status()).toBe(404);
  expect(media.headers()['x-content-type-options']).toBe('nosniff');
  expect(media.headers()['content-security-policy']).toBe("default-src 'none'; sandbox");

  const stat = await request.get('/static/admin/css/base.css');
  expect(stat.status()).toBe(200);
  expect(stat.headers()['x-content-type-options']).toBe('nosniff');
});

test('7.1 HSTS не віддається по http', async ({ request }) => {
  test.skip(TLS_STAND, 'на TLS-стенді HSTS обов’язковий (тест нижче)');
  const res = await request.get('/', { maxRedirects: 0 });
  expect(res.headers()['strict-transport-security']).toBeUndefined();
});

test('7.1 у консолі головної і калькулятора немає порушень CSP', async ({ page }) => {
  const violations: string[] = [];
  page.on('console', (msg) => {
    if (/Content Security Policy|Content-Security-Policy/i.test(msg.text())) violations.push(msg.text());
  });
  for (const path of ['/', '/calculator']) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
  }
  expect(violations).toEqual([]);
});

test('7.1 /login не вбудовується в iframe чужого сайту (clickjacking, C7)', async ({ page, baseURL, browserName }) => {
  test.skip(browserName !== 'chromium', 'URL заблокованого фрейму перевіряється лише в Chromium');
  await page.route('http://embed.example.test/', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: `<iframe id="f" src="${baseURL}/login" width="600" height="400"></iframe>`,
    }),
  );
  await page.goto('http://embed.example.test/');
  await expect
    .poll(() => page.frames().map((f) => f.url()).join(' '), { timeout: 10_000 })
    .toContain('chrome-error');
  expect(page.frames().some((f) => f.url().endsWith('/login'))).toBe(false);
});

test('7.1 запит більше NGINX_MAX_BODY_SIZE на /api/ -> 413 з JSON detail', async ({ request }) => {
  const res = await request.post('/api/v1/auth/token/', {
    headers: { 'content-type': 'application/octet-stream' },
    data: Buffer.alloc(25 * 1024 * 1024),
  });
  expect(res.status()).toBe(413);
  expect(res.headers()['content-type']).toContain('application/json');
  expect(typeof (await res.json()).detail).toBe('string');
});

// У e2e-стеку NGINX_AUTH_RATE=6000r/m (docker-compose.e2e.yml), боевий ліміт тут не діє.
// Перевірено на відрендереному конфігу через `docker run nginx:alpine` (PROGRESS 7.1): 12-й запит -> 429 JSON.
test.fixme('7.1-429: 12 швидких POST /api/v1/auth/token/ -> 429 JSON -> окремий стенд з бойовим NGINX_AUTH_RATE', async () => {});

test.describe('TLS-стенд (TLS_MODE=selfsigned)', () => {
  test.skip(!TLS_STAND, 'потрібен E2E_TLS_STAND=1 і https-стенд');

  test('7.1 https віддає HSTS без preload (за замовчуванням)', async ({ request }) => {
    const res = await request.get('/', { maxRedirects: 0 });
    const hsts = res.headers()['strict-transport-security'];
    expect(hsts).toMatch(/^max-age=\d+$/);
    expect(hsts).not.toContain('preload');
  });

  test('7.1 http://localhost/listings -> 301 на https', async ({ playwright }) => {
    const ctx = await playwright.request.newContext();
    const res = await ctx.get('http://localhost/listings', { maxRedirects: 0 });
    expect(res.status()).toBe(301);
    expect(res.headers()['location']).toBe('https://localhost/listings');
    await ctx.dispose();
  });
});
