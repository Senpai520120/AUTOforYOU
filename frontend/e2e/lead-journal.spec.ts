/**
 * E2E: журнал заявок і атрибуція (задача 2.15): код AFY, згода партнера, кваліфікація,
 * статус партнера, CSV без ПДн, заборона видалення, доступ до CSV за ролями.
 */
import fs from 'fs';
import type { Page } from '@playwright/test';
import { test, expect, storageStatePath } from './fixtures';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const PHONE_DIGITS = '671234567';
const NAME = '[E2E] Журнал';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(consentInit);
});

async function startForm(page: Page) {
  await page.goto('/calculator');
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  await expect(page.getByRole('heading', { name: 'Залишити заявку брокеру' })).toBeVisible();
  return page.getByTestId('lead-form');
}

test.describe('Гість і брокер', () => {
  test('без згоди партнера кнопка заблокована; із згодою показано код, брокер кваліфікує і качає CSV', async ({ page, browser }) => {
    const form = await startForm(page);
    await form.getByLabel("Ім'я").fill(NAME);
    await form.getByLabel('Телефон').fill('067 123 45 67');
    await form.getByLabel(/обробку персональних даних/).check();
    const submit = form.getByRole('button', { name: 'Надіслати' });
    await expect(submit).toBeDisabled();
    await form.getByLabel(/передачу моїх контактних даних партнеру/).check();
    await expect(submit).toBeEnabled();
    await submit.click();
    const success = page.getByTestId('lead-success');
    await expect(success).toContainText(/AFY-\d{4}-\d+/);
    const code = (await success.innerText()).match(/AFY-\d{4}-\d+/)![0];

    const ctx = await browser.newContext({ storageState: storageStatePath('broker') });
    const broker = await ctx.newPage();
    await broker.addInitScript(consentInit);
    await broker.goto('/broker/leads');
    await broker.getByLabel('Ім’я або телефон').fill(NAME);
    await broker.getByRole('button', { name: 'Знайти' }).click();
    await broker.getByTestId('broker-lead-item').filter({ hasText: code }).getByRole('link').click();
    await expect(broker.getByRole('heading', { name: code })).toBeVisible();
    await expect(broker.getByTestId('lead-qualification')).toHaveText('Не оцінено');

    for (const question of ['Бюджет не нижче порога', 'Термін не більше 3 місяців', 'Знає про ремонт']) {
      const radio = broker.getByRole('radio', { name: new RegExp(`Так — ${question}`) });
      await radio.click();
      await expect(radio).toBeChecked();
    }
    const no = broker.getByRole('radio', { name: /Ні — Готовий до депозиту/ });
    await no.click();
    await expect(no).toBeChecked();
    await expect(broker.getByTestId('lead-qualification')).toHaveText('Гаряча');

    await broker.getByLabel('Статус за словами партнера').selectOption('deposit');
    await expect(broker.getByLabel('Статус за словами партнера')).toHaveValue('deposit');

    await broker.goto('/broker/leads');
    const [download] = await Promise.all([
      broker.waitForEvent('download'),
      broker.getByRole('link', { name: 'Завантажити CSV' }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^leads-.*\.csv$/);
    const text = fs.readFileSync((await download.path())!, 'utf-8');
    expect(text).toContain(code);
    expect(text).not.toContain(PHONE_DIGITS);
    expect(text).not.toContain(NAME);
    await ctx.close();
  });
});

test.describe('Обхід і права', () => {
  test('брокер не може видалити заявку через API (405)', async ({ api }) => {
    const broker = await api('broker');
    const list = await broker.get('/api/v1/broker/leads/');
    expect(list.status()).toBe(200);
    const results = (await list.json()).results as { id: number }[];
    test.skip(results.length === 0, 'немає заявок для перевірки');
    const resp = await broker.delete(`/api/v1/broker/leads/${results[0].id}/`);
    expect(resp.status()).toBe(405);
  });

  test('CSV: клієнт без ролі отримує 403, анонім 401, брокер 200', async ({ api, request }) => {
    const path = '/api/v1/broker/leads/export.csv';
    expect((await request.get(path)).status()).toBe(401);
    expect((await (await api('buyer')).get(path)).status()).toBe(403);
    const ok = await (await api('broker')).get(path);
    expect(ok.status()).toBe(200);
    expect(ok.headers()['content-type']).toContain('text/csv');
  });
});
