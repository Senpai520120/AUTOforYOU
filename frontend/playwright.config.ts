import { defineConfig, devices } from '@playwright/test';

/**
 * Тести ганяються проти стека, піднятого через docker compose:
 * nginx віддає сайт на http://localhost (порт 80).
 * Для dev-режиму (`npm run dev`) задати E2E_BASE_URL=http://localhost:3000.
 *
 * Захист від запуску на проді: хост має бути в білому списку, інакше
 * потрібен явний E2E_ALLOW_REMOTE=1 (лише для @smoke).
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost';
const ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'nginx', 'frontend'];
const host = new URL(baseURL).hostname;
if (!ALLOWED_HOSTS.includes(host) && process.env.E2E_ALLOW_REMOTE !== '1') {
  throw new Error(
    `E2E_BASE_URL (${host}) не в білому списку (${ALLOWED_HOSTS.join(', ')}); ` +
      'для smoke задайте E2E_ALLOW_REMOTE=1',
  );
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,

  reporter: [
    ['list'],
    // open: 'never' — щоб браузер не відкривався сам після кожного прогону.
    ['html', { open: 'never' }],
  ],

  use: {
    baseURL,
    locale: 'uk-UA',
    timezoneId: 'Europe/Kyiv',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  // TLS-стенд (TLS_MODE=selfsigned, задача 7.1): только security-headers.spec.ts, без логина
  // (NEXT_PUBLIC_API_URL собран под http), самоподписанный сертификат разрешён.
  projects: (process.env.E2E_TLS_STAND === '1'
    ? [
        {
          name: 'tls',
          testMatch: /security-headers\.spec\.ts/,
          use: { ...devices['Desktop Chrome'], ignoreHTTPSErrors: true },
        },
      ]
    : [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    // Smoke после деплоя (задача 7.5): только чтение, без логина (нет зависимости от setup) - годится и для боевого сайта
    // (E2E_BASE_URL=https://... E2E_ALLOW_REMOTE=1 npx playwright test --project=smoke).
    {
      name: 'smoke',
      testMatch: /(^|[\/])smoke\.spec\.ts$/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      grepInvert: /@mobile/,
      testIgnore: /(^|[\/])smoke\.spec\.ts$/, // этот файл гоняет проект smoke
      dependencies: ['setup'],
    },
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 7'] },
      grep: /@mobile/,
      dependencies: ['setup'],
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 13'] },
      grep: /@mobile/,
      dependencies: ['setup'],
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
      grep: /@smoke/,
      dependencies: ['setup'],
    },
  ]
  // Против чужого хоста (E2E_ALLOW_REMOTE=1, например боевой сайт после деплоя) запускается только read-only проект smoke:
  // остальные проекты логинятся тестовыми пользователями и пишут данные.
  ).filter((project) => process.env.E2E_ALLOW_REMOTE !== '1' || project.name === 'smoke'),
});
