/**
 * E2E: «Як працює пригон» і FAQ (задача 2.13).
 *
 * /how-it-works і підвал рендеряться на сервері Next і кешуються на 60 с, page.route їх не
 * перехоплює. Сид e2e_seed створює активні записи «[E2E] …» (чернетки з міграції лишаються
 * неактивними), тому на сидованому стеку перевіряємо заповнений стан, а порожній — лише коли
 * контенту немає (інакше test.skip). Блок FAQ під калькулятором клієнтський: його емулюємо
 * через page.route.
 */
import { test, expect } from './fixtures';

const API = process.env.E2E_API_URL ?? 'http://localhost';
const FAQ_URL = '**/api/v1/content/faq/**';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('cookie_consent', 'necessary'));
});

test.use({ storageState: { cookies: [], origins: [] } });

async function isPublished(request: import('@playwright/test').APIRequestContext): Promise<boolean> {
  const data = await (await request.get(`${API}/api/v1/content/how-it-works/`)).json();
  return data.published === true;
}

test.describe('Сторінка «Як працює пригон»', () => {
  test('успіх: етапи по порядку, FAQ розкривається, посилання на калькулятор і в підвалі', async ({ page, request }) => {
    test.skip(!(await isPublished(request)), 'немає опублікованого контенту (стек без e2e_seed)');
    test.setTimeout(120_000);
    // Сторінка й підвал кешуються на 60 с: якщо їх відкрили до e2e_seed, перезавантажуємо, поки не оновиться.
    await expect(async () => {
      await page.goto('/how-it-works');
      await expect(page.getByTestId('import-step').first()).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });

    const steps = page.getByTestId('import-step');
    await expect(steps).toHaveCount(3);
    await expect(steps.nth(0)).toContainText('[E2E] Етап перший');
    await expect(steps.nth(1)).toContainText('[E2E] Етап другий');
    await expect(steps.nth(2)).toContainText('[E2E] Етап третій');

    const item = page.getByTestId('faq-block').getByTestId('faq-item').first();
    await item.getByText('[E2E] Питання для сторінки?').click();
    await expect(item).toContainText('[E2E] Відповідь 1');

    expect(await page.content()).not.toContain('ПЕРЕВІРИТИ');
    await expect(page.getByRole('link', { name: 'Розрахувати вартість' })).toHaveAttribute('href', '/calculator');

    await expect(async () => {
      await page.goto('/how-it-works');
      await expect(page.locator('footer').getByRole('link', { name: 'Як працює пригон' })).toBeVisible({ timeout: 2000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
    await page.locator('footer').getByRole('link', { name: 'Як працює пригон' }).click();
    await expect(page).toHaveURL(/\/how-it-works$/);
  });

  test("обхід: без опублікованих записів - 200, «Інформація скоро з'явиться», без позначок, noindex", async ({ page, request }) => {
    test.skip(await isPublished(request), 'на стеку є опублікований контент (сид e2e): порожній стан недосяжний');
    const res = await page.goto('/how-it-works');
    expect(res?.status()).toBe(200);
    await expect(page.getByTestId('how-it-works-empty')).toContainText("Інформація скоро з'явиться");
    await expect(page.getByTestId('import-step')).toHaveCount(0);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
    expect(await page.content()).not.toContain('ПЕРЕВІРИТИ');
    await expect(page.locator('footer').getByRole('link', { name: 'Як працює пригон' })).toHaveCount(0);
  });
});

test.describe('FAQ під калькулятором', () => {
  test('успіх: запис із прапорцем показується й розкривається', async ({ page }) => {
    await page.route(FAQ_URL, route =>
      route.fulfill({ json: { faq: [{ question: 'Тестове питання?', answer: 'Рядок 1\nРядок 2' }] } }));
    await page.goto('/calculator');
    const block = page.getByTestId('calculator-faq');
    await expect(block).toBeVisible();
    const item = block.getByTestId('faq-item').first();
    await item.getByText('Тестове питання?').click();
    await expect(item).toContainText('Рядок 2');
  });

  test('успіх: без перехоплення показується питання з сиду для калькулятора', async ({ page, request }) => {
    const data = await (await request.get(`${API}/api/v1/content/faq/?place=calculator`)).json();
    test.skip(data.faq.length === 0, 'немає FAQ для калькулятора (стек без e2e_seed)');
    await page.goto('/calculator');
    await expect(page.getByTestId('calculator-faq')).toContainText('[E2E] Питання для калькулятора?');
    await expect(page.getByTestId('calculator-faq')).not.toContainText('[E2E] Питання для сторінки?');
  });

  test('обхід: порожній список - блок не показується', async ({ page }) => {
    await page.route(FAQ_URL, route => route.fulfill({ json: { faq: [] } }));
    await page.goto('/calculator');
    await expect(page.getByRole('heading', { name: 'Калькулятор вартості «під ключ»' })).toBeVisible();
    await expect(page.getByTestId('calculator-faq')).toHaveCount(0);
  });

  test('помилка: API 500 - сторінка калькулятора працює, блоку немає', async ({ page }) => {
    await page.route(FAQ_URL, route => route.fulfill({ status: 500, json: { detail: 'x' } }));
    await page.goto('/calculator');
    await expect(page.getByRole('heading', { name: 'Калькулятор вартості «під ключ»' })).toBeVisible();
    await expect(page.getByTestId('calculator-faq')).toHaveCount(0);
  });

  test('обхід: <script> у відповіді виводиться текстом і не виконується', async ({ page }) => {
    let executed = false;
    await page.exposeFunction('__xss', () => { executed = true; });
    await page.route(FAQ_URL, route =>
      route.fulfill({ json: { faq: [{ question: 'Q', answer: '<script>window.__xss()</script><img src=x onerror="window.__xss()">' }] } }));
    await page.goto('/calculator');
    const item = page.getByTestId('calculator-faq').getByTestId('faq-item');
    await item.getByText('Q', { exact: true }).click();
    await expect(item).toContainText('<script>window.__xss()</script>');
    expect(executed).toBe(false);
  });
});
