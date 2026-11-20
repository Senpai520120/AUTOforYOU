/** Форми слова для українських числівників: one (1, 21), few (2–4), many (0, 5–20), other (дроби). */
export interface UkForms {
  one: string;
  few: string;
  many: string;
  other?: string;
}

const rules = new Intl.PluralRules('uk');

/** pluralUk(5, {one:'оголошення', few:'оголошення', many:'оголошень'}) → «оголошень». */
export function pluralUk(n: number, forms: UkForms): string {
  const cat = rules.select(n);
  if (cat === 'one' || cat === 'few' || cat === 'many') return forms[cat];
  return forms.other ?? forms.many;
}

/** «1 оголошення», «2 оголошення», «5 оголошень». */
export const listingsCount = (n: number) =>
  `${n} ${pluralUk(n, { one: 'оголошення', few: 'оголошення', many: 'оголошень' })}`;
