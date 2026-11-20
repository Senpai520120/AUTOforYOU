import type { LeadStatus } from './types';

/** Підписи статусів заявки для клієнта (шаг 6, задача 2.3). */
export const LEAD_STATUS_LABELS: Record<LeadStatus, string> = {
  new: 'Нова',
  in_progress: 'У роботі',
  contract: 'Договір',
  car_bought: 'Авто куплено',
  in_transit: 'В дорозі',
  customs: 'Розмитнення',
  delivered: 'Видано',
  rejected: 'Відмова',
  spam: 'Спам',
};

export function leadStatusLabel(status: string, fallback = ''): string {
  return (LEAD_STATUS_LABELS as Record<string, string>)[status] || fallback || status;
}

/** Згоди (задача 1.14): тексти чекбокса 18+ і помилок, щоб не розмазувати по компонентах. */
export const COOKIE_SETTINGS_LABEL = 'Налаштування cookie';
export const AGE_18_LABEL = 'Мені виповнилося 18 років';
export const AGE_18_REQUIRED = 'Підтвердіть, що вам виповнилося 18 років';

/** Сторінки довіри (задача 2.13). */
export const HOW_IT_WORKS_LABEL = 'Як працює пригон';
export const FAQ_LABEL = 'Питання та відповіді';
export const HOW_IT_WORKS_SOON = "Інформація скоро з'явиться";
export const CALC_COST_LABEL = 'Розрахувати вартість';

/** Назви сторінок для хлібних крихт (задача 9.54). */
export const HOME_LABEL = 'Головна';
export const CALCULATOR_LABEL = 'Калькулятор вартості';
export const LANDING_INDEX_LABEL = 'Пригон авто з США';

/** Єдині назви (задача 10.18): розділ каталогу, послуга, головна кнопка шапки. */
export const CATALOG_LABEL = 'Каталог Україна';
export const SERVICE_LABEL = LANDING_INDEX_LABEL;
export const PRIMARY_CTA_LABEL = 'Порахувати';

/** Підписи нижньої мобільної панелі картки (6.6): уточнюються при приймання в одному місці. */
export const MOBILE_BAR_LABELS = {
  call: 'Подзвонити',
  write: 'Написати',
  calculate: 'Розрахувати',
  lead: 'Залишити заявку',
} as const;

/** Довіра до продавця (задача 8.6). */
export const VERIFIED_DEALER_LABEL = 'Перевірений дилер';
export const SELLER_ALL_LISTINGS_LABEL = 'Усі оголошення продавця';
export const SELLER_NOT_FOUND = 'Продавця не знайдено';
export const SAFE_DEAL_RULES_LABEL = 'Правила безпечної угоди';
export const POSTING_AS_DEALER = 'Ви публікуєте як перевірений дилер';

const MONTHS_GENITIVE = [
  'січня', 'лютого', 'березня', 'квітня', 'травня', 'червня',
  'липня', 'серпня', 'вересня', 'жовтня', 'листопада', 'грудня',
];

/** «2026-03» → «на сайті з березня 2026»; некоректне значення → ''. */
export function memberSinceLabel(value: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})$/.exec(value ?? '');
  if (!m) return '';
  const month = MONTHS_GENITIVE[Number(m[2]) - 1];
  return month ? `на сайті з ${month} ${m[1]}` : '';
}
export const ABOUT_LABEL = 'Про нас';
