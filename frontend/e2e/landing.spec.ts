/**
 * E2E: сторінки моделей «Пригон з США» (задача 2.16b).
 *
 * Дані: e2e_seed створює опубліковану `e2e-toyota-camry` (розрахунок за ставками з seed_rates) і чернетку
 * `e2e-draft`. SSR і sitemap кешуються fetch'ем (LANDING_REVALIDATE_SECONDS), а сторінки могли відкрити
 * до e2e_seed, тому перші перевірки обгорнуті в toPass з перезавантаженням. Суми беремо з публічного API
 * і порівнюємо з тим, що показано: фронт нічого не рахує.
 */
import type { Page, Request } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

const API = process.env.E2E_API_URL ?? 'http://localhost';
const SLUG = 'e2e-toyota-camry';
const URL = `/prigon/${SLUG}`;
const LEADS_URL = (r: Request) => r.url().endsWith('/api/v1/leads/') && r.method() === 'POST';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.use({ storageState: { cookies: [], origins: [] } });

async function openLanding(page: Page) {
  await expect(async () => {
    await page.goto(URL);
    await expect(page.getByTestId('landing-total-usd')).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 90_000, intervals: [5_000] });
}

const digits = (s: string | null) => Number((s ?? '').replace(/\D/g, ''));

async function fillLead(page: Page, name: string, consent = true) {
  const form = page.getByTestId('lead-form');
  await form.getByLabel("Ім'я").fill(name);
  await form.getByLabel('Телефон').fill('0671234567');
  if (consent) await form.getByLabel(/обробку персональних даних/).check();
  await form.getByLabel(/передачу моїх контактних даних партнеру/).check();
}

test.describe('Сторінка моделі', () => {
  test('успіх: H1, підсумок = API, «орієнтовний», дата ставок, термін, SEO, sitemap, форма передзаповнена', async ({ page, request }) => {
    test.setTimeout(150_000);
    await openLanding(page);
    const api = await (await request.get(`${API}/api/v1/landings/${SLUG}/`)).json();

    await expect(page.getByTestId('landing-h1')).toHaveText('Пригон [E2E] Toyota Camry з США — ціна під ключ');
    // 9.51: перелік «що не входить» — той самий, що в API (текст правиться в адмінці)
    expect(api.calculation.exclusions.length).toBeGreaterThan(0);
    await expect(page.getByTestId('calc-exclusions')).toContainText(api.calculation.exclusions[0]);
    expect(digits(await page.getByTestId('landing-total-usd').textContent()))
      .toBe(Math.round(Number(api.calculation.total_usd_full)));
    // 10.1: «РАЗОМ» включає акциз, ПДВ і пенсійний збір, тож строго більше суми без митних платежів
    expect(Number(api.calculation.total_usd_full)).toBeGreaterThan(Number(api.calculation.total_usd));
    expect(digits(await page.getByTestId('landing-total-uah').textContent()))
      .toBe(Math.round(Number(api.calculation.total_uah)));
    await expect(page.getByTestId('landing-estimate')).toHaveText('Орієнтовний розрахунок');
    const [y, m, d] = (api.calculation.rates_valid_from as string).split('-');
    await expect(page.getByTestId('landing-rates-date')).toContainText(`${d}.${m}.${y}`);
    await expect(page.getByTestId('landing-term')).toContainText('[E2E] 2-3 місяці');
    await expect(page.getByTestId('landing-included')).toContainText('[E2E] Аукціонний збір');
    await expect(page.getByTestId('landing-disclaimer')).toContainText('Послугу пригону надає партнер');
    await expect(page.getByTestId('landing-calc-link')).toHaveAttribute('href', /^\/calculator\?.*engine_cc=2000/);
    await expect(page.getByRole('navigation', { name: 'Корисні посилання' }).getByRole('link', { name: 'Як працює пригон' })).toHaveAttribute('href', '/how-it-works');

    // SEO: canonical, OG, robots не noindex.
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', new RegExp(`/prigon/${SLUG}$`));
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', /Пригон \[E2E\] Toyota Camry з США/);
    await expect(page.locator('meta[property="og:image"]')).toHaveCount(1);
    // Кореневий layout завжди віддає robots «index, follow»; перевіряємо, що noindex немає.
    expect(await page.locator('meta[name="robots"]').getAttribute('content')).not.toContain('noindex');
    expect(await page.content()).not.toContain('ПЕРЕВІРИТИ');

    // Форма передзаповнена маркою/моделлю й бюджетом з розрахунку; липкої панелі на десктопі немає.
    await expect(page.getByTestId('lead-vehicle')).toContainText('[E2E] Toyota Camry');
    await expect(page.getByLabel(/Бюджет/)).toHaveValue(String(Math.round(Number(api.calculation.total_usd_full))));
    await expect(page.getByTestId('landing-mobile-bar')).toBeHidden();

    // Sitemap: сторінка є, чернетки немає.
    await expect(async () => {
      const xml = await (await request.get('/sitemap.xml')).text();
      expect(xml).toContain(`/prigon/${SLUG}`);
      expect(xml).not.toContain('/prigon/e2e-draft');
    }).toPass({ timeout: 60_000, intervals: [5_000] });
  });

  test('заявка: 201, source=landing, код AFY; підміна сум у запиті не змінює снимок', async ({ page, request, api }) => {
    test.setTimeout(150_000);
    await openLanding(page);
    const landing = await (await request.get(`${API}/api/v1/landings/${SLUG}/`)).json();
    const name = `[E2E] Лендінг ${Date.now()}`;
    // Клієнт «підміняє» суми й снимок: сервер має їх ігнорувати.
    await page.route((u) => u.pathname.endsWith('/api/v1/leads/'), async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      const body = route.request().postDataJSON();
      await route.continue({
        postData: JSON.stringify({ ...body, total_usd: '1.00', total_usd_full: '1.00', total_uah: '1.00', calculation_snapshot: { total_usd: '1.00', total_usd_full: '1.00' } }),
      });
    });
    await fillLead(page, name);
    const [resp, req] = await Promise.all([
      page.waitForResponse((r) => LEADS_URL(r.request())),
      page.waitForRequest(LEADS_URL),
      page.getByTestId('lead-form').getByRole('button', { name: 'Надіслати' }).click(),
    ]);
    expect(resp.status()).toBe(201);
    expect(req.postDataJSON()).toMatchObject({ source: 'landing', landing_slug: SLUG });
    await expect(page.getByTestId('lead-success')).toContainText(/Заявку №AFY-\d{4}-\d+ отримано/);

    const broker = await api('broker');
    const list = await (await broker.get(`/api/v1/broker/leads/?search=${encodeURIComponent(name)}`)).json();
    expect(list.results).toHaveLength(1);
    const detail = await (await broker.get(`/api/v1/broker/leads/${list.results[0].id}/`)).json();
    expect(detail.calculation_snapshot.total_usd).toBe(landing.calculation.total_usd);
    expect(detail.calculation_snapshot.total_usd_full).toBe(landing.calculation.total_usd_full);
  });

  test('без згоди на обробку ПДн запит не йде', async ({ page }) => {
    test.setTimeout(150_000);
    await openLanding(page);
    await fillLead(page, '[E2E] Без згоди', false);
    await expectNoRequest(page, LEADS_URL, async () => {
      await page.getByTestId('lead-form').getByRole('button', { name: 'Надіслати' }).click();
    });
    await expect(page.getByText('Потрібна згода на обробку персональних даних.')).toBeVisible();
  });

  test('обхід: чернетка й неіснуюча сторінка - 404, у sitemap їх немає', async ({ page, request }) => {
    for (const slug of ['e2e-draft', 'no-such-model']) {
      const res = await page.goto(`/prigon/${slug}`);
      expect(res?.status()).toBe(404);
      expect((await request.get(`${API}/api/v1/landings/${slug}/`)).status()).toBe(404);
    }
    const xml = await (await request.get('/sitemap.xml')).text();
    expect(xml).not.toContain('no-such-model');
    expect(xml).not.toContain('e2e-draft');
  });

  test('індекс /prigon: опубліковані моделі є, чернетки немає', async ({ page }) => {
    test.setTimeout(150_000);
    await expect(async () => {
      await page.goto('/prigon');
      await expect(page.getByTestId('landing-index-item').first()).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await expect(page.getByTestId('landing-index')).toContainText('[E2E] Toyota Camry');
    await expect(page.getByTestId('landing-index')).not.toContainText('Чернетка');
  });

  test('«Як працює пригон»: блок популярних моделей веде на сторінку моделі', async ({ page }) => {
    test.setTimeout(150_000);
    await expect(async () => {
      await page.goto('/how-it-works');
      await expect(page.getByTestId('popular-model').first()).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await page.getByTestId('popular-models').getByRole('link', { name: '[E2E] Toyota Camry' }).click();
    await expect(page).toHaveURL(new RegExp(`/prigon/${SLUG}$`));
  });

  test('перехід у калькулятор: ціна передзаповнена; сміття в параметрі не ламає сторінку', async ({ page, request }) => {
    test.setTimeout(150_000);
    await openLanding(page);
    const api = await (await request.get(`${API}/api/v1/landings/${SLUG}/`)).json();
    await page.getByTestId('landing-calc-link').click();
    await expect(page).toHaveURL(/\/calculator\?.*auction_price_usd=/);
    await expect(page.locator('#auction_price_usd')).toHaveValue(String(Number(api.calculation.inputs.auction_price_usd)));
    for (const junk of ['abc', '-5', '0', '99999999999', '<script>']) {
      const res = await page.goto(`/calculator?auction_price_usd=${encodeURIComponent(junk)}`);
      expect(res?.status()).toBe(200);
      await expect(page.locator('#auction_price_usd')).toHaveValue('10000');
    }
  });

  // Задача 10.9: ссылки на лендинги (шапка, подвал, главная), крошки, «Схожі моделі».
  // Серверный кеш fetch (LANDING_REVALIDATE_SECONDS) мог запомнить пустой список до e2e_seed: toPass с перезагрузкой.
  test('шапка: «Пригон авто з США» веде на /prigon @smoke', async ({ page }) => {
    test.setTimeout(150_000);
    await expect(async () => {
      await page.goto('/calculator');
      await expect(page.getByRole('banner').getByRole('link', { name: 'Пригон авто з США' })).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await page.getByRole('banner').getByRole('link', { name: 'Пригон авто з США' }).click();
    await expect(page).toHaveURL(/\/prigon$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Пригон авто з США' })).toBeVisible();
  });

  test('підвал: «Пригон авто з США» веде на /prigon @smoke', async ({ page }) => {
    test.setTimeout(150_000);
    await expect(async () => {
      await page.goto('/calculator');
      await expect(page.getByTestId('footer-link-prigon')).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await page.getByTestId('footer-link-prigon').click();
    await expect(page).toHaveURL(/\/prigon$/);
  });

  test('головна: «Популярні моделі» з [E2E] Toyota Camry, без чернетки, веде на сторінку моделі @smoke', async ({ page }) => {
    test.setTimeout(150_000);
    await expect(async () => {
      await page.goto('/');
      await expect(page.getByTestId('popular-models')).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    const block = page.getByTestId('popular-models');
    await expect(block).not.toContainText('Чернетка');
    await expect(block.getByTestId('popular-model').first()).toBeVisible();
    await expect(block.getByRole('link', { name: 'Усі моделі' })).toHaveAttribute('href', '/prigon');
    await block.getByRole('link', { name: '[E2E] Toyota Camry' }).click();
    await expect(page).toHaveURL(new RegExp(`/prigon/${SLUG}$`));
  });

  test('сторінка моделі: видимі крихти збігаються з BreadcrumbList, остання без посилання @smoke', async ({ page }) => {
    test.setTimeout(150_000);
    await openLanding(page);
    const nav = page.getByRole('navigation', { name: 'Хлібні крихти' });
    const items = nav.getByRole('listitem');
    await expect(items).toHaveCount(3);
    await expect(nav.getByRole('link')).toHaveCount(2);
    await expect(nav.getByRole('link', { name: 'Головна' })).toHaveAttribute('href', '/');
    await expect(nav.getByRole('link', { name: 'Пригон авто з США' })).toHaveAttribute('href', '/prigon');
    const last = nav.locator('[aria-current="page"]');
    await expect(last).toHaveCount(1);
    await expect(last).toHaveText('[E2E] Toyota Camry');
    await expect(last).not.toHaveAttribute('href', /.*/);

    const ld = await page.locator('script[type="application/ld+json"]').allTextContents();
    const list = ld.map((t) => JSON.parse(t)).flat().find((b) => b['@type'] === 'BreadcrumbList');
    const names = list.itemListElement.map((c: { name: string }) => c.name);
    expect(names).toEqual(['Головна', 'Пригон авто з США', '[E2E] Toyota Camry']);
    const html = (await items.allTextContents()).map((t) => t.replace('›', '').trim());
    expect(html).toEqual(names);
  });

  test('сторінка моделі: «Схожі моделі» з іншою моделлю, без поточної, не довші ліміту (6) @smoke', async ({ page }) => {
    test.setTimeout(150_000);
    // e2e_seed публікує два [E2E]-лендинги однієї марки: Toyota Camry (поточний) і Honda Accord.
    await expect(async () => {
      await page.goto(URL);
      await expect(page.getByTestId('similar-models')).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    const block = page.getByTestId('similar-models');
    await expect(block.getByRole('link', { name: '[E2E] Honda Accord' })).toHaveAttribute('href', '/prigon/e2e-honda-accord');
    await expect(block).not.toContainText('Toyota Camry');
    await expect(block).not.toContainText('Чернетка');
    expect(await block.getByTestId('popular-model').count()).toBeLessThanOrEqual(6);
  });

  test('10.10: «Коротко про модель» і FAQ на Camry; FAQPage JSON-LD збігається з питаннями', async ({ page }) => {
    test.setTimeout(150_000);
    await openLanding(page);
    const facts = page.getByTestId('model-facts');
    await expect(facts).toContainText('Коротко про модель');
    await expect(facts).toContainText('[E2E] XV70');
    await expect(facts).toContainText('Бензин');
    await expect(facts).toContainText('2000 см³');
    const faq = page.getByTestId('model-faq');
    await expect(faq.getByTestId('model-faq-item')).toHaveCount(2);
    await faq.getByText('[E2E] Перше питання?').click();
    await expect(faq.getByText('[E2E] Перша відповідь.')).toBeVisible();
    await expect(page.getByText('[E2E] Неактивне питання?')).toHaveCount(0);

    const ld = await page.locator('script[type="application/ld+json"]').allTextContents();
    const block = ld.map((t) => JSON.parse(t)).flat().find((b) => b['@type'] === 'FAQPage');
    expect(block['@context']).toBe('https://schema.org');
    const names = block.mainEntity.map((q: { name: string }) => q.name);
    expect(names).toEqual(['[E2E] Перше питання?', '[E2E] Друге питання?']);
    expect(block.mainEntity[0].acceptedAnswer.text).toBe('[E2E] Перша відповідь.');
  });

  test('10.10: без FAQ і без покоління (Honda Accord) блоку FAQ і FAQPage немає', async ({ page }) => {
    test.setTimeout(150_000);
    await expect(async () => {
      await page.goto('/prigon/e2e-honda-accord');
      await expect(page.getByTestId('landing-h1')).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await expect(page.getByTestId('model-faq')).toHaveCount(0);
    await expect(page.getByText('Поширені запитання')).toHaveCount(0);
    await expect(page.getByTestId('model-facts')).not.toContainText('Покоління');
    const ld = await page.locator('script[type="application/ld+json"]').allTextContents();
    const types = ld.map((t) => JSON.parse(t)).flat().map((b) => b['@type']);
    expect(types).not.toContain('FAQPage');
  });

  test.fixme('LAND-2 → пункт «Пригон» і блок «Популярні моделі» приховані при порожньому довіднику (потрібен стек без опублікованих лендингів)', async () => {});

  test.fixme('LAND-1 → SSR-запит Next не перехоплюється page.route: чесну помилку при недоступному API перевірити на стеку без backend', async () => {});
});

test.describe('Сторінка моделі на мобільному @mobile', () => {
  test('липка панель «Залишити заявку» видима й веде до форми', async ({ page }) => {
    test.setTimeout(150_000);
    await openLanding(page);
    const bar = page.getByTestId('landing-mobile-bar');
    await expect(bar).toBeVisible();
    await bar.getByRole('button', { name: 'Залишити заявку' }).click();
    await expect(page.getByTestId('lead-form')).toBeInViewport();
    await expect(page.getByLabel("Ім'я")).toBeFocused();
  });

  test('бургер-меню: «Пригон авто з США» веде на /prigon', async ({ page }) => {
    test.setTimeout(150_000);
    await expect(async () => {
      await page.goto('/calculator');
      await page.getByRole('button', { name: 'Меню' }).click();
      await expect(page.getByRole('navigation', { name: 'Мобільне меню' }).getByRole('link', { name: 'Пригон авто з США' })).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await page.getByRole('navigation', { name: 'Мобільне меню' }).getByRole('link', { name: 'Пригон авто з США' }).click();
    await expect(page).toHaveURL(/\/prigon$/);
  });
});
