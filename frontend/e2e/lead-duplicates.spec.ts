/**
 * E2E: захист від дубля заявки (задача 10.13): один POST при подвійному кліку, той самий Idempotency-Key
 * при повторі після обриву, 409 для чужого ключа, ключ не згоряє при невалідній формі.
 */
import type { Page, Request } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

const LEADS_URL = (r: Request) => r.url().endsWith('/api/v1/leads/') && r.method() === 'POST';
const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');

test.beforeEach(async ({ page }) => {
  await page.addInitScript(consentInit);
});

async function calculate(page: Page) {
  await page.goto('/calculator');
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  await expect(page.getByRole('heading', { name: 'Залишити заявку брокеру' })).toBeVisible();
}

async function fillLead(page: Page, phone: string) {
  const form = page.getByTestId('lead-form');
  await form.getByLabel("Ім'я").fill('[E2E] Дубль');
  await form.getByLabel('Телефон').fill(phone);
  await form.getByLabel(/обробку персональних даних/).check();
  await form.getByLabel(/передачу моїх контактних даних партнеру/).check();
}

const submitBtn = (page: Page) => page.getByTestId('lead-form').getByRole('button', { name: 'Надіслати' });
// Унікальний телефон на прогон: інакше повтор у вікні 60 хв створив би заявку-повтор.
const uniquePhone = () => `+3805${String(Date.now()).slice(-8)}`;

test.describe('Захист від дубля заявки', () => {
  test('подвійний клік і Enter двічі дають один POST і один екран успіху', async ({ page }) => {
    await calculate(page);
    await fillLead(page, uniquePhone());
    const posts: Request[] = [];
    page.on('request', (r) => { if (LEADS_URL(r)) posts.push(r); });
    await expect(submitBtn(page)).toBeEnabled();
    await submitBtn(page).dblclick();
    await expect(page.getByTestId('lead-success')).toContainText(/Заявку №AFY-\d{4}-\d+ отримано/);
    expect(posts).toHaveLength(1);
    expect(posts[0].headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/);
  });

  test('повтор після обриву йде з тим самим Idempotency-Key, заявка одна', async ({ page }) => {
    await calculate(page);
    await fillLead(page, uniquePhone());
    const keys: (string | undefined)[] = [];
    let first = true;
    await page.route('**/api/v1/leads/', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      keys.push(route.request().headers()['idempotency-key']);
      if (first) {
        first = false;
        return route.abort();
      }
      return route.continue();
    });
    await expect(submitBtn(page)).toBeEnabled();
    await submitBtn(page).click();
    await expect(page.getByText('Не вдалося надіслати заявку')).toBeVisible();
    await expect(submitBtn(page)).toBeEnabled();
    await submitBtn(page).click();
    await expect(page.getByTestId('lead-success')).toBeVisible();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
  });

  test('той самий ключ з іншим телефоном дає 409 без номера чужої заявки', async ({ page, request }) => {
    await calculate(page);
    const phone = uniquePhone();
    await fillLead(page, phone);
    const [req] = await Promise.all([page.waitForRequest(LEADS_URL), submitBtn(page).click()]);
    const key = req.headers()['idempotency-key'];
    const created = await (await req.response())!.json();
    await expect(page.getByTestId('lead-success')).toBeVisible();

    const other = `+3806${String(Date.now()).slice(-8)}`;
    const resp = await request.post('/api/v1/leads/', {
      headers: { 'Idempotency-Key': key },
      data: {
        name: '[E2E] Чужий', phone: other, source: 'landing', consent: true, partner_consent: true,
      },
    });
    expect(resp.status()).toBe(409);
    const text = await resp.text();
    expect(text).toContain('Ця заявка вже надіслана з іншими даними');
    expect(text).not.toContain(created.public_id);
    expect(text).not.toContain(phone);
  });

  test('після «Новий розрахунок» ключ інший', async ({ page }) => {
    await calculate(page);
    await fillLead(page, uniquePhone());
    const [first] = await Promise.all([page.waitForRequest(LEADS_URL), submitBtn(page).click()]);
    await expect(page.getByTestId('lead-success')).toBeVisible();
    await page.getByRole('button', { name: 'Новий розрахунок' }).click();
    await calculate(page);
    await fillLead(page, uniquePhone());
    const [second] = await Promise.all([page.waitForRequest(LEADS_URL), submitBtn(page).click()]);
    expect(second.headers()['idempotency-key']).not.toBe(first.headers()['idempotency-key']);
  });

  test('порожній телефон: запит не йде', async ({ page }) => {
    await calculate(page);
    await fillLead(page, '');
    await expectNoRequest(page, LEADS_URL, async () => {
      await expect(submitBtn(page)).toBeEnabled();
      await submitBtn(page).click();
    });
    await expect(page.getByText('Вкажіть телефон.')).toBeVisible();
  });
});
