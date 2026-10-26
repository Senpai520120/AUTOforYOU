/**
 * E2E: SEO (задача 6.3a): sitemap, robots, canonical, noindex, title юр. сторінок, редірект лота.
 * OG-картинки і блок «OG» - задача 6.3b.
 * Режим стека (C2C, LOTS) читається з /api/v1/site-settings/; блоки чужих режимів пропускаються з причиною.
 */
import type { APIRequestContext } from '@playwright/test';
import { test, expect } from './fixtures';

const GUEST = { cookies: [], origins: [] };
const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const LEGAL = ['/privacy', '/terms', '/rules', '/refund', '/cookies'] as const;

type Item = { id: number; status?: string; vehicle_detail?: { make: string; model: string; year: number } };
let c2c = false;
let lots = false;
let localIds: number[] = [];
let lotSlugs: { id: number; slug: string }[] = [];

async function allPages(ctx: APIRequestContext, path: string): Promise<Item[]> {
  const out: Item[] = [];
  for (let page = 1; page < 500; page++) {
    const res = await ctx.get(`${path}${path.includes('?') ? '&' : '?'}page=${page}`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    out.push(...body.results);
    if (!body.next) break;
  }
  return out;
}

const sitemapPaths = (xml: string) =>
  [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => new URL(m[1]).pathname);
// Формат как в lib/utils.ts::listingSlug.
const slugOf = (l: Item) => {
  const v = l.vehicle_detail!;
  return `${l.id}-${`${v.make}-${v.model}-${v.year}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`;
};
const canonicalPath = async (page: import('@playwright/test').Page) =>
  new URL((await page.locator('link[rel="canonical"]').getAttribute('href'))!).pathname;

test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });
  const s = await (await ctx.get('/api/v1/site-settings/')).json();
  c2c = s.c2c_enabled === true;
  lots = s.lots_enabled === true;
  if (c2c) localIds = (await allPages(ctx, '/api/v1/local/listings/')).map((l) => l.id);
  if (lots) {
    const items = [
      ...(await allPages(ctx, '/api/v1/listings/?status=in_stock')),
      ...(await allPages(ctx, '/api/v1/listings/?status=in_transit')),
    ];
    lotSlugs = items.map((l) => ({ id: l.id, slug: slugOf(l) }));
  }
  await ctx.dispose();
});

test.describe('SEO: метадані сторінок', () => {
  test.use({ storageState: GUEST });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  for (const path of ['/', ...LEGAL]) {
    test(`${path}: title з AUTOforYOU рівно один раз, description, canonical, lang=uk @smoke`, async ({ page }) => {
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(200);
      const title = await page.title();
      expect(title.split('AUTOforYOU').length - 1, title).toBe(1);
      await expect(page.locator('html')).toHaveAttribute('lang', 'uk');
      const desc = await page.locator('meta[name="description"]').getAttribute('content');
      expect((desc ?? '').length).toBeGreaterThan(20);
      expect((desc ?? '').length).toBeLessThanOrEqual(160);
      expect(await canonicalPath(page)).toBe(path);
      expect(await page.locator('link[rel="canonical"]').getAttribute('href')).not.toContain('?');
    });
  }

  test('/ua: canonical без query; з page - індексується, з фільтром - noindex', async ({ page }) => {
    test.skip(!c2c, 'C2C вимкнено: /ua віддає «Скоро»');
    await page.goto('/ua?page=2');
    expect(await canonicalPath(page)).toBe('/ua');
    expect(await page.locator('meta[name="robots"]').getAttribute('content')).not.toContain('noindex');

    await page.goto('/ua?fuel_type=diesel');
    expect(await canonicalPath(page)).toBe('/ua');
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  });

  test('картка місцевого оголошення: canonical /local/<id>, title без подвійного суфікса', async ({ page }) => {
    test.skip(!c2c || localIds.length === 0, 'C2C вимкнено або немає активних оголошень (e2e_seed)');
    const id = localIds[0];
    const resp = await page.goto(`/local/${id}`);
    expect(resp?.status()).toBe(200);
    expect(await canonicalPath(page)).toBe(`/local/${id}`);
    const title = await page.title();
    expect(title.split('AUTOforYOU').length - 1, title).toBe(1);
    const desc = await page.locator('meta[name="description"]').getAttribute('content');
    expect((desc ?? '').length).toBeLessThanOrEqual(160);
  });

  test('картка лота: canonical = slug-URL', async ({ page }) => {
    test.skip(!lots || lotSlugs.length === 0, 'LOTS_ENABLED=false (ВОЛНА-1) або лотів немає');
    const { slug } = lotSlugs[0];
    await page.goto(`/listings/${slug}`);
    expect(await canonicalPath(page)).toBe(`/listings/${slug}`);
  });
});

test.describe('SEO: noindex на закритих і приватних сторінках', () => {
  test.use({ storageState: GUEST });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  // /me і /local/new гостя редіректить proxy.ts на /login (теж noindex) - перевіряємо кінцеву сторінку.
  // /b2b і /dealers/apply на ВОЛНІ-1 - 404, а Next додає noindex і до 404.
  for (const path of ['/me', '/login', '/register', '/b2b', '/local/new', '/dealers/apply', '/calculator']) {
    test(`${path}: meta robots містить noindex`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute('content', /noindex/);
    });
  }

  test('/calculator: noindex, але OG-теги збережено', async ({ page }) => {
    await page.goto('/calculator');
    await expect(page.locator('meta[property="og:title"]')).toHaveCount(1);
    await expect(page.locator('meta[property="og:site_name"]')).toHaveAttribute('content', 'AUTOforYOU');
    await expect(page.locator('meta[property="og:locale"]')).toHaveAttribute('content', 'uk_UA');
  });

  test('pending-оголошення: 404 для гостя', async ({ api, page }) => {
    test.skip(!c2c, 'C2C вимкнено');
    const seller = await api('seller');
    const mine = await (await seller.get('/api/v1/local/my-listings/')).json();
    const pending = (mine.results ?? mine).find((l: { status: string }) => l.status === 'pending');
    test.skip(!pending, 'у фікстурі немає pending-оголошення продавця');
    const resp = await page.goto(`/local/${pending.id}`);
    expect(resp?.status()).toBe(404);
  });
});

test.describe('SEO: sitemap.xml', () => {
  test('статичні сторінки є, приватні й /calculator відсутні, порівняння по точному шляху', async ({ request }) => {
    const res = await request.get('/sitemap.xml');
    expect(res.status()).toBe(200);
    const paths = sitemapPaths(await res.text());
    for (const p of ['/', ...LEGAL]) expect(paths, p).toContain(p);
    for (const p of ['/me', '/b2b', '/local/new', '/calculator', '/login', '/register', '/dealers/apply']) {
      expect(paths, p).not.toContain(p);
    }
  });

  test('/ua є точним елементом <loc> при увімкненому C2C', async ({ request }) => {
    test.skip(!c2c, 'C2C вимкнено: /ua у sitemap не включається');
    expect(sitemapPaths(await (await request.get('/sitemap.xml')).text())).toContain('/ua');
  });

  test('усі активні місцеві оголошення (усі сторінки API) є в sitemap, pending - немає', async ({ request, api }) => {
    test.skip(!c2c, 'C2C вимкнено: оголошень у sitemap немає');
    const paths = sitemapPaths(await (await request.get('/sitemap.xml')).text());
    const inMap = paths.filter((u) => /^\/local\/\d+$/.test(u)).sort();
    expect(inMap).toEqual(localIds.map((id) => `/local/${id}`).sort());

    const seller = await api('seller');
    const mine = await (await seller.get('/api/v1/local/my-listings/')).json();
    for (const l of (mine.results ?? mine).filter((x: { status: string }) => x.status === 'pending')) {
      expect(paths).not.toContain(`/local/${l.id}`);
    }
  });

  test('лоти у sitemap мають slug-URL; при LOTS_ENABLED=false /listings немає', async ({ request }) => {
    const paths = sitemapPaths(await (await request.get('/sitemap.xml')).text());
    if (!lots) {
      expect(paths.filter((u) => u.startsWith('/listings'))).toEqual([]);
      return;
    }
    expect(paths.filter((u) => /^\/listings\/.+/.test(u)).sort()).toEqual(
      lotSlugs.map((l) => `/listings/${l.slug}`).sort(),
    );
  });
});

test.describe('SEO: robots.txt', () => {
  test('закриває приватні розділи, але не /media/', async ({ request }) => {
    const res = await request.get('/robots.txt');
    expect(res.status()).toBe(200);
    const lines = (await res.text()).split(/\r?\n/);
    for (const rule of ['/me$', '/me/', '/b2b$', '/b2b/', '/dealers/', '/local/new', '/local/*/edit', '/login', '/register', '/admin/', '/api/']) {
      expect(lines, rule).toContain(`Disallow: ${rule}`);
    }
    // Голе `/me` закрило б за префіксом /media/ (фото оголошень).
    expect(lines).not.toContain('Disallow: /me');
    expect(lines.filter((l) => l.startsWith('Disallow: /media'))).toEqual([]);
    expect(lines).not.toContain('Disallow: /calculator');
    expect(lines.some((l) => l.startsWith('Sitemap: ') && l.endsWith('/sitemap.xml'))).toBe(true);
  });
});

test.describe('SEO: канонічна адреса лота (308)', () => {
  test('/listings/<id> і /listings/<id>-мусор → 308 на slug-URL', async ({ request }) => {
    test.skip(!lots || lotSlugs.length === 0, 'LOTS_ENABLED=false (ВОЛНА-1) або лотів немає');
    const { id, slug } = lotSlugs[0];
    for (const raw of [`${id}`, `${id}-wrong-tail`]) {
      const res = await request.get(`/listings/${raw}`, { maxRedirects: 0 });
      expect(res.status(), raw).toBe(308);
      expect(new URL(res.headers()['location'], 'http://x').pathname).toBe(`/listings/${slug}`);
    }
    expect((await request.get(`/listings/${slug}`, { maxRedirects: 0 })).status()).toBe(200);
  });

  test('при LOTS_ENABLED=false /listings/<id> → 404, а не редірект', async ({ request }) => {
    test.skip(lots, 'LOTS_ENABLED=true');
    const res = await request.get('/listings/1-toyota-camry-2020', { maxRedirects: 0 });
    expect(res.status()).toBe(404);
  });
});
