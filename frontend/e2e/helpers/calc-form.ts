import type { Page } from '@playwright/test';

// 10.17: поля калькулятора порожні за замовчуванням (лише placeholder-підказки). Тести, що рахують, вводять значення самі.
const DEFAULTS = { price: '10000', engineCc: '2000', year: '2020' };

/** Заповнює порожні обов'язкові поля (ціна, об'єм, рік); те, що тест уже ввів чи що прийшло з query, не чіпає. */
export async function fillCalcForm(page: Page, values: Partial<typeof DEFAULTS> = {}) {
  const v = { ...DEFAULTS, ...values };
  const fields: [string, string][] = [
    ['Ціна аукціону ($)', v.price],
    ["Об'єм двигуна (см³)", v.engineCc],
    ['Рік випуску', v.year],
  ];
  for (const [label, value] of fields) {
    const input = page.getByLabel(label, { exact: true });
    if ((await input.inputValue()) === '') await input.fill(value);
  }
}
