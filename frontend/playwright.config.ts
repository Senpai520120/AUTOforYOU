import { defineConfig, devices } from '@playwright/test';

/**
 * Тести ганяються проти стека, піднятого через `docker compose up -d`:
 * nginx віддає сайт на http://localhost (порт 80). Порт 3000 живе тільки
 * всередині контейнера і назовні не проброшений.
 *
 * Для dev-режиму (`npm run dev`) задати E2E_BASE_URL=http://localhost:3000.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,

  reporter: [
    ['list'],
    // open: 'never' — щоб браузер не відкривався сам після кожного прогону.
    // Звіт дивитись через `npm run test:e2e:report`.
    ['html', { open: 'never' }],
  ],

  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost',

    // Раніше стояло on-first-retry при retries: 0 локально — повторів не буває,
    // отже trace не писався ніколи і подивитись його було неможливо.
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
