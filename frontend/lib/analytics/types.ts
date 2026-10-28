/**
 * Адаптери веб-аналітики (задача 3.5).
 *
 * Провайдер додається однією реалізацією цього інтерфейсу й записом у `PROVIDERS` (index.ts);
 * пікселі Meta/TikTok заплановані в «Рост» (9.29) і підключаються так само.
 */

/** Публічні ID з /api/v1/site-settings/ (поле analytics). Порожній об'єкт = аналітики немає. */
export interface PublicAnalytics {
  ga4_id?: string;
  cloudflare_token?: string;
}

/** Параметри події: лише категорії. Жодних імен, телефонів, email, id заявок і текстів. */
export type EventParams = { source?: 'calculator' | 'listing' | 'landing' | 'register' };

export interface AnalyticsProvider {
  readonly key: string;
  /** true — вмикається лише після «Прийняти всі»; false — працює без cookie й без згоди. */
  readonly requiresConsent: boolean;
  /** Ключ у PublicAnalytics, звідки береться ID. */
  readonly settingKey: keyof PublicAnalytics;
  /** Перевірка формату ID: невалідний ID = провайдер вимкнено, нічого не вставляється. */
  isValidId(id: string): boolean;
  load(id: string): void;
  /** Прибрати скрипт, вимкнути відправку, видалити cookie провайдера. */
  unload(): void;
  /** Надіслати подію. Викликається лише коли провайдер завантажений. */
  track(event: string, params: EventParams): void;
  /** Перегляд сторінки при зміні маршруту (SPA). Необов'язковий. */
  pageView?(): void;
}
