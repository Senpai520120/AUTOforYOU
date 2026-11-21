/**
 * 11.15-VIS: візуальні тести ключових сторінок (toHaveScreenshot).
 *
 * Базові знімки НЕ в репозиторії: шрифти та рендер Windows і Linux відрізняються, тому
 * знімати їх треба тільки в CI-оточенні (Linux), інакше CI буде червоним. Поки знімків немає,
 * тести оформлено як test.fixme. Як зняти базу (з frontend/, стек e2e піднято за правилами CLAUDE.md):
 *   1) прибрати `.fixme` нижче (замінити на `test`);
 *   2) npx playwright test visual.spec.ts --project=chromium --update-snapshots
 *      (у Linux-контейнері, напр. mcr.microsoft.com/playwright, або в CI);
 *   3) закомітити e2e/visual.spec.ts-snapshots/*-chromium-linux.png.
 * Далі `npx playwright test visual.spec.ts --project=chromium` порівнює з базою.
 *
 * maxDiffPixelRatio 0.02: допускає до 2% відмінних пікселів: дрібне згладжування тексту між
 * прогонами; зсув макета чи кольору кнопки значно перевищує цей поріг. Динаміка (курс, дати,
 * сітка оголошень каталогу) маскується.
 */
import { test, expect } from './fixtures';

const SHOT = { maxDiffPixelRatio: 0.02, animations: 'disabled' as const, fullPage: true };

const PAGES = [
  { name: 'home', path: '/' },
  { name: 'calculator', path: '/calculator' },
  { name: 'catalog-ua', path: '/ua' },
];

test.describe('11.15-VIS візуальні знімки', () => {
  test.skip(({ browserName }) => browserName !== 'chromium', 'знімки лише Chromium');

  for (const p of PAGES) {
    test.fixme(`11.15-VIS → снять базовые снимки в CI (Linux) командой --update-snapshots: ${p.name}`, async ({ page }) => {
      await page.addInitScript(() => {
        window.localStorage.setItem('cookie_consent', 'necessary');
      });
      await page.goto(p.path);
      await page.waitForLoadState('networkidle');
      // Динамічні блоки: картки оголошень, дати/курси (елементи з data-dynamic), cookie-банер.
      const masks = [
        page.locator('article'),
        page.locator('[data-dynamic]'),
        page.locator('time'),
        page.getByRole('dialog'),
      ];
      await expect(page).toHaveScreenshot(`${p.name}.png`, { ...SHOT, mask: masks });
    });
  }
});
