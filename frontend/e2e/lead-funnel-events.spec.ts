/**
 * E2E: події воронки без ПДн (задача 10.15): lead_form_start - рівно один за перший ввід,
 * lead_submit_error - при відповіді 500 на відправку заявки.
 */
import type { Page, Request } from '@playwright/test';
import { test, expect } from './fixtures';
import { expectNoRequest } from './helpers/network';

const consentInit = () => window.localStorage.setItem('cookie_consent', 'necessary');
const isMetric = (key: string) => (r: Request) =>
  r.url().endsWith('/api/v1/metrics/event/') && r.method() === 'POST' && r.postData() === JSON.stringify({ key });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(consentInit);
});

async function openForm(page: Page) {
  await page.goto('/calculator');
  await page.getByRole('button', { name: 'Розрахувати' }).click();
  await expect(page.getByRole('heading', { name: 'Залишити заявку брокеру' })).toBeVisible();
}

test.describe('Події воронки заявки', () => {
  test('перший ввід шле рівно один lead_form_start, наступний - ні', async ({ page }) => {
    await openForm(page);
    const starts: Request[] = [];
    page.on('request', (r) => { if (isMetric('lead_form_start')(r)) starts.push(r); });
    const form = page.getByTestId('lead-form');
    await form.getByLabel("Ім'я").fill('[E2E] Старт');
    await expect.poll(() => starts.length).toBe(1);
    await expectNoRequest(page, isMetric('lead_form_start'), async () => {
      await form.getByLabel('Телефон').fill('+380501112233');
    });
    expect(starts).toHaveLength(1);
  });

  test('відповідь 500 на відправку шле lead_submit_error', async ({ page }) => {
    await openForm(page);
    await page.route('**/api/v1/leads/', (route) =>
      route.request().method() === 'POST'
        ? route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
        : route.fallback());
    const errors: Request[] = [];
    page.on('request', (r) => { if (isMetric('lead_submit_error')(r)) errors.push(r); });
    const form = page.getByTestId('lead-form');
    await form.getByLabel("Ім'я").fill('[E2E] Помилка');
    await form.getByLabel('Телефон').fill('+380501112244');
    await form.getByLabel(/обробку персональних даних/).check();
    await form.getByLabel(/передачу моїх контактних даних партнеру/).check();
    const submit = form.getByRole('button', { name: 'Надіслати' });
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(page.getByText('Не вдалося надіслати заявку')).toBeVisible();
    await expect.poll(() => errors.length).toBe(1);
  });
});
