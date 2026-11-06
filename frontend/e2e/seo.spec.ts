/**
 * E2E: SEO (задача 6.3a): sitemap, robots, canonical, noindex, title юр. сторінок, редірект лота.
 * Блок «OG» (задача 6.3b): теги превью, картинки opengraph-image, закриті об-єкти.
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

// ---------------------------------------------------------------------------------------------
// OG (задача 6.3b): теги превью і картинки. Картинку тягнемо за path з og:image на baseURL стека:
// SITE_URL у збірці може бути бойовим доменом, якого з тест-середовища не видно.
// ---------------------------------------------------------------------------------------------
test.describe('OG: теги і картинки превью', () => {
  test.use({ storageState: GUEST });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  type Pg = import('@playwright/test').Page;
  const meta = (page: Pg, sel: string) => page.locator(`meta[${sel}]`).first().getAttribute('content');

  async function expectFullPreview(page: Pg, request: APIRequestContext, path: string) {
    const resp = await page.goto(path);
    expect(resp?.status(), path).toBe(200);
    const canonical = (await page.locator('link[rel="canonical"]').getAttribute('href'))!;
    expect(await meta(page, 'property="og:title"'), path).toBeTruthy();
    const desc = await meta(page, 'property="og:description"');
    expect((desc ?? '').length).toBeGreaterThan(0);
    expect((desc ?? '').length).toBeLessThanOrEqual(160);
    expect(await meta(page, 'property="og:url"')).toBe(canonical);
    expect(canonical).not.toContain('?');
    // Не втрачені при перевизначенні openGraph сторінкою (пастка злиття з layout).
    expect(await meta(page, 'property="og:site_name"')).toBe('AUTOforYOU');
    expect(await meta(page, 'property="og:locale"')).toBe('uk_UA');
    expect(await meta(page, 'property="og:image:alt"')).toBeTruthy();
    expect(await meta(page, 'name="twitter:card"')).toBe('summary_large_image');
    const image = (await meta(page, 'property="og:image"'))!;
    expect(image, path).toMatch(/^https?:\/\//);
    expect(new URL(image).protocol).toBe(new URL(canonical).protocol);
    expect(await meta(page, 'name="twitter:image"')).toBe(image);
    const url = new URL(image);
    const img = await request.get(url.pathname + url.search);
    expect(img.status(), image).toBe(200);
    expect(img.headers()['content-type']).toBe('image/png');
    expect((await img.body()).length).toBeGreaterThan(1000);
    // Бренд-картинку (/, /calculator, юр. сторінки) від картки з даними відрізняє службовий заголовок.
    const expectedVariant = /^\/(local|listings)\/[^/]+/.test(path) ? undefined : 'brand';
    if (expectedVariant) expect(img.headers()['x-og-variant'], path).toBe(expectedVariant);
    else expect(['item', 'photo'], path).toContain(img.headers()['x-og-variant']);
    return image;
  }

  for (const path of ['/', '/calculator', '/privacy']) {
    test(`${path}: повний набір OG/Twitter, картинка 200 image/png @smoke`, async ({ page, request }) => {
      await expectFullPreview(page, request, path);
    });
  }

  test('/ua: OG-набір; з фільтром og:url лишається /ua', async ({ page, request }) => {
    test.skip(!c2c, 'C2C вимкнено: /ua віддає «Скоро»');
    await expectFullPreview(page, request, '/ua');
    await page.goto('/ua?fuel_type=diesel');
    expect(new URL((await meta(page, 'property="og:url"'))!).pathname).toBe('/ua');
  });

  test('/listings: OG-набір; з фільтром og:url = /listings', async ({ page, request }) => {
    test.skip(!lots, 'LOTS_ENABLED=false (ВОЛНА-1): /listings віддає 404');
    await expectFullPreview(page, request, '/listings');
    await page.goto('/listings?make=bmw');
    expect(new URL((await meta(page, 'property="og:url"'))!).pathname).toBe('/listings');
  });

  test('/calculator: одночасно noindex і OG-картинка', async ({ page }) => {
    await page.goto('/calculator');
    await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute('content', /noindex/);
    await expect(page.locator('meta[property="og:image"]')).toHaveCount(1);
  });

  test('місцеве оголошення: повний OG-набір, картка 200 image/png', async ({ page, request }) => {
    test.skip(!c2c || localIds.length === 0, 'C2C вимкнено або немає активних оголошень (e2e_seed)');
    await expectFullPreview(page, request, `/local/${localIds[0]}`);
  });

  test('лот: повний OG-набір; режим фото off - в og:image немає фото Copart/IAAI і зовнішніх хостів', async ({ page, request }) => {
    test.skip(!lots || lotSlugs.length === 0, 'LOTS_ENABLED=false (ВОЛНА-1) або лотів немає');
    const image = await expectFullPreview(page, request, `/listings/${lotSlugs[0].slug}`);
    // og:image - генерована картка цього ж сайту, а не фото аукціону.
    expect(new URL(image).pathname).toMatch(/^\/listings\/[^/]+\/opengraph-image/);
    for (const host of ['copart', 'iaai']) expect(image.toLowerCase()).not.toContain(host);
    expect(await page.content()).not.toMatch(/<meta[^>]+(og:image|twitter:image)[^>]+(copart|iaai)/i);
  });

  test('неіснуюче або некоректне оголошення: картинка 404', async ({ request }) => {
    test.skip(!c2c, 'C2C вимкнено: покриває тест нижче');
    expect((await request.get('/local/99999999/opengraph-image')).status()).toBe(404);
    expect((await request.get('/local/abc/opengraph-image')).status()).toBe(404);
  });

  test('/local: картинка існуючого активного оголошення - 200 при C2C, 404 при вимкненому розділі', async ({ api, request }) => {
    // Існуючий id беремо з API (або з кабінету продавця, якщо розділ закрито), щоб 404 не міг бути просто «немає запису».
    let id = localIds[0];
    if (!c2c) {
      const mine = await (await (await api('seller')).get('/api/v1/local/my-listings/')).json();
      id = (mine.results ?? mine).find((l: { status: string }) => l.status === 'active')?.id;
    }
    test.skip(!id, 'у фікстурі немає активного оголошення (e2e_seed)');
    const res = await request.get(`/local/${id}/opengraph-image`);
    expect(res.status()).toBe(c2c ? 200 : 404);
  });

  test('/listings: картинка існуючого лота - 200 при LOTS_ENABLED, 404 при вимкненому модулі', async ({ api, request }) => {
    let slug: string | undefined = lotSlugs[0]?.slug;
    if (!lots) {
      // Лотів у публічному API при вимкненому модулі немає: беремо id напряму з кабінету персоналу.
      const res = await (await api('staff')).get('/api/v1/listings/?page=1');
      const first = res.status() === 200 ? ((await res.json()).results ?? [])[0] : undefined;
      slug = first ? slugOf(first) : undefined;
    }
    test.skip(!slug, 'у фікстурі немає лота (e2e_seed)');
    const res = await request.get(`/listings/${slug}/opengraph-image`);
    expect(res.status()).toBe(lots ? 200 : 404);
    if (lots) expect(res.headers()['x-og-variant']).toBe('item');
  });

  test('pending/приховане оголошення: 404 на сторінку і на картинку, у HTML немає og з даними', async ({ api, request }) => {
    test.skip(!c2c, 'C2C вимкнено');
    const seller = await api('seller');
    const mine = await (await seller.get('/api/v1/local/my-listings/')).json();
    const closed = (mine.results ?? mine).filter((l: { status: string }) => ['pending', 'hidden', 'rejected'].includes(l.status));
    test.skip(closed.length === 0, 'у фікстурі немає pending/hidden-оголошень продавця');
    for (const l of closed) {
      const page = await request.get(`/local/${l.id}`);
      expect(page.status(), `page ${l.id}`).toBe(404);
      expect(await page.text()).not.toMatch(/property="og:title" content="[^"]*(Toyota|Camry)/);
      expect((await request.get(`/local/${l.id}/opengraph-image`)).status(), `image ${l.id}`).toBe(404);
    }
  });

  test('картка активного оголошення віддається як image/png (кирилиця - пікселі вручну)', async ({ api, request }) => {
    test.skip(!c2c || localIds.length === 0, 'C2C вимкнено або немає активних оголошень');
    const seller = await api('seller');
    const mine = await (await seller.get('/api/v1/local/my-listings/')).json();
    const active = (mine.results ?? mine).find((l: { status: string }) => l.status === 'active');
    test.skip(!active, 'немає активного оголошення продавця');
    // Фікстури з «ЇЄІҐ» у e2e_seed поки немає: перевіряємо код і тип, вигляд літер - вручну (LAUNCH_CHECKLIST).
    const res = await request.get(`/local/${active.id}/opengraph-image`);
    expect(res.status()).toBe(200);
    expect(res.headers()['content-type']).toBe('image/png');
    // У seed у активного оголошення є фото (e2e_seed кладе FIXTURE_PHOTOS); якщо файл не знайдено, seed створює без фото.
    expect(['photo', 'item']).toContain(res.headers()['x-og-variant']);
  });
});

// ─── JSON-LD і текст /calculator (задача 9.54) ───────────────────────────────

type Ld = Record<string, unknown>;
const ldBlocks = async (page: import('@playwright/test').Page): Promise<Ld[]> =>
  (await page.locator('script[type="application/ld+json"]').allTextContents()).map((t) => JSON.parse(t) as Ld);
/** Жодного порожнього значення (рядка, null, порожнього об'єкта) у розмітці. */
const noEmpty = (v: unknown): boolean => {
  if (v === null || v === undefined || v === '') return false;
  if (Array.isArray(v)) return v.every(noEmpty);
  if (typeof v === 'object') return Object.values(v as object).every(noEmpty);
  return true;
};
const crumbs = (b: Ld) => (b.itemListElement as { position: number; name: string; item: string }[]);

test.describe('SEO: JSON-LD (9.54)', () => {
  test.use({ storageState: GUEST });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  test('головна: Organization і WebSite, контакти збігаються з налаштуваннями сайту, порожніх значень немає', async ({ page, request }) => {
    const s = await (await request.get('/api/v1/site-settings/')).json();
    await page.goto('/');
    const blocks = await ldBlocks(page);
    expect(blocks.map((b) => b['@type']).sort()).toEqual(['Organization', 'WebSite']);
    for (const b of blocks) {
      expect(b['@context']).toBe('https://schema.org');
      expect(noEmpty(b)).toBe(true);
    }
    const org = blocks.find((b) => b['@type'] === 'Organization')!;
    const site = blocks.find((b) => b['@type'] === 'WebSite')!;
    expect(org.name).toBe('AUTOforYOU');
    expect(site.name).toBe('AUTOforYOU');
    expect(new URL(org.url as string).pathname).toBe('/');
    // Контакти - лише з налаштувань: є в API - є в розмітці, немає - ключа теж немає.
    const email = s.support_email || s.privacy_email;
    if (s.phone) expect(org.telephone).toBe(s.phone); else expect(org).not.toHaveProperty('telephone');
    if (email) expect(org.email).toBe(email); else expect(org).not.toHaveProperty('email');
    if (s.owner_legal_name) expect(String(org.legalName)).toContain(s.owner_legal_name);
    else expect(org).not.toHaveProperty('legalName');
    if (s.owner_code) expect(JSON.stringify(blocks)).not.toContain(s.owner_code);
  });

  test('головна без хлібних крихт, внутрішні сторінки без Organization', async ({ page }) => {
    await page.goto('/');
    expect((await ldBlocks(page)).some((b) => b['@type'] === 'BreadcrumbList')).toBe(false);
    await page.goto('/prigon');
    expect((await ldBlocks(page)).some((b) => b['@type'] === 'Organization')).toBe(false);
  });

  const PAGES = [
    { path: '/prigon', names: ['Головна', 'Пригон авто з США'], urls: ['/', '/prigon'] },
    { path: '/calculator', names: ['Головна', 'Калькулятор вартості'], urls: ['/', '/calculator'] },
    { path: '/how-it-works', names: ['Головна', 'Як працює пригон'], urls: ['/', '/how-it-works'] },
  ];
  for (const p of PAGES) {
    test(`${p.path}: BreadcrumbList з позиціями, назвами й абсолютними адресами @smoke`, async ({ page }) => {
      await page.goto(p.path);
      if (p.path === '/how-it-works' && (await page.getByTestId('how-it-works-empty').count())) {
        test.skip(true, 'сторінка не опублікована: розмітки немає, сторінка noindex');
      }
      const lists = (await ldBlocks(page)).filter((b) => b['@type'] === 'BreadcrumbList');
      expect(lists).toHaveLength(1);
      expect(noEmpty(lists[0])).toBe(true);
      expect(crumbs(lists[0]).map((c) => c.position)).toEqual(p.names.map((_, i) => i + 1));
      expect(crumbs(lists[0]).map((c) => c.name)).toEqual(p.names);
      expect(crumbs(lists[0]).map((c) => new URL(c.item).pathname)).toEqual(p.urls);
    });
  }

  test('сторінка моделі: крихти Головна → Пригон → модель', async ({ page, request }) => {
    const list = await (await request.get('/api/v1/landings/')).json();
    const slug = (list.results ?? list)[0]?.slug as string | undefined;
    test.skip(!slug, 'у стеку немає опублікованих сторінок моделей');
    await page.goto(`/prigon/${slug}`);
    const [b] = (await ldBlocks(page)).filter((x) => x['@type'] === 'BreadcrumbList');
    expect(crumbs(b).map((c) => c.position)).toEqual([1, 2, 3]);
    expect(crumbs(b).map((c) => new URL(c.item).pathname)).toEqual(['/', '/prigon', `/prigon/${slug}`]);
    expect(crumbs(b)[2].name.length).toBeGreaterThan(0);
  });

  test('CSP не блокує сторінки з розміткою: порушень script-src немає, розмітка читається', async ({ page }) => {
    await page.addInitScript(() => {
      (window as unknown as { __csp: string[] }).__csp = [];
      document.addEventListener('securitypolicyviolation', (e) =>
        (window as unknown as { __csp: string[] }).__csp.push(e.violatedDirective));
    });
    for (const path of ['/', '/prigon', '/calculator']) {
      await page.goto(path);
      expect((await ldBlocks(page)).length).toBeGreaterThan(0);
      const violations = await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
      expect(violations.filter((v) => v.startsWith('script-src'))).toEqual([]);
    }
  });
});

test.describe('JSON-LD: побудова розмітки без браузера (9.54)', () => {
  const SITE = { name: 'AUTOforYOU', url: 'https://example.test' };
  const KEYS = ['@context', '@type', 'name', 'url'];

  test('порожні й пробільні реквізити не виводяться', async () => {
    const { buildOrganizationLd } = await import('../lib/jsonld-core');
    expect(Object.keys(buildOrganizationLd(SITE)).sort()).toEqual(KEYS);
    expect(Object.keys(buildOrganizationLd(SITE, { telephone: '   ', address: '\n', email: '', legalName: ' ' })).sort())
      .toEqual(KEYS);
    const full = buildOrganizationLd(SITE, { legalName: 'ФОП Іваненко І. І.', telephone: '+380501112233',
      email: 'help@example.test', address: 'м. Київ, вул. Тестова, 1' });
    expect(full).toMatchObject({ legalName: 'ФОП Іваненко І. І.', telephone: '+380501112233', email: 'help@example.test',
      address: { '@type': 'PostalAddress', streetAddress: 'м. Київ, вул. Тестова, 1' } });
  });

  test('sameAs лише з http(s)-адреси', async () => {
    const { buildOrganizationLd } = await import('../lib/jsonld-core');
    expect(buildOrganizationLd(SITE, { sameAs: 'javascript:alert(1)' })).not.toHaveProperty('sameAs');
    expect(buildOrganizationLd(SITE, { sameAs: 'https://t.me/afy' })).toHaveProperty('sameAs', ['https://t.me/afy']);
  });

  test('текст із адмінки не закриває <script>: <, >, & і U+2028 екрановані, JSON повертається без змін', async () => {
    const { buildOrganizationLd, jsonLdString } = await import('../lib/jsonld-core');
    const evil = '</script><script>alert(1)</script> & x\u2028y\u2029z';
    const text = jsonLdString(buildOrganizationLd(SITE, { legalName: evil, address: evil }));
    for (const ch of ['<', '>', '&', '\u2028', '\u2029']) expect(text).not.toContain(ch);
    expect(JSON.parse(text).legalName).toBe(evil);
    expect(JSON.parse(text).address.streetAddress).toBe(evil);
  });

  test('крихти: порожня назва відкидається, позиції без пропусків, адреси абсолютні', async () => {
    const { buildBreadcrumbLd } = await import('../lib/jsonld-core');
    const ld = buildBreadcrumbLd(SITE.url, [{ name: 'A', path: '/' }, { name: '  ', path: '/x' }, { name: 'B', path: '/b' }]);
    expect(ld.itemListElement).toEqual([
      { '@type': 'ListItem', position: 1, name: 'A', item: 'https://example.test/' },
      { '@type': 'ListItem', position: 2, name: 'B', item: 'https://example.test/b' },
    ]);
  });
});

test.describe('SEO: /calculator - текст, canonical, noindex (9.54)', () => {
  test.use({ storageState: GUEST });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(consentInit);
  });

  test('H1, блок «Як рахуємо» без цифр, посилання на /prigon і /how-it-works', async ({ page }) => {
    await page.goto('/calculator');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Калькулятор вартості/);
    const block = page.getByTestId('calculator-how-we-count');
    await expect(block).toBeVisible();
    await expect(block.getByRole('heading', { name: 'Як рахуємо' })).toBeVisible();
    expect(await block.textContent()).not.toMatch(/\d/);
    await expect(block.getByRole('link', { name: 'Пригон за моделями' })).toHaveAttribute('href', '/prigon');
    await expect(block.getByRole('link', { name: 'Як працює пригон' })).toHaveAttribute('href', '/how-it-works');
  });

  test('адреса з query: canonical на /calculator без query, noindex лишається', async ({ page }) => {
    await page.goto('/calculator?auction_price_usd=5000&year=2019&utm_source=tg');
    const href = (await page.locator('link[rel="canonical"]').getAttribute('href'))!;
    expect(new URL(href).pathname + new URL(href).search).toBe('/calculator');
    await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute('content', /noindex/);
  });

  test('/calculator не в sitemap (noindex знімається лише після звірки ставок)', async ({ request }) => {
    const xml = await (await request.get('/sitemap.xml')).text();
    expect(sitemapPaths(xml)).not.toContain('/calculator');
  });

  test('внутрішні посилання: /prigon → калькулятор, /how-it-works → /prigon', async ({ page }) => {
    await page.goto('/prigon');
    await expect(page.getByTestId('prigon-link-calculator')).toHaveAttribute('href', '/calculator');
    await page.goto('/how-it-works');
    test.skip((await page.getByTestId('how-it-works-empty').count()) > 0, 'сторінка не опублікована');
    await expect(page.getByTestId('how-link-prigon')).toHaveAttribute('href', '/prigon');
  });
});
