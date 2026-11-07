/**
 * Згода на використання сховища браузера.
 *
 * Вхід в акаунт живе в httpOnly-cookie access/refresh і cookie csrftoken (задача 1.4) —
 * вони строго необхідні, згоди не потребують. Сам вибір зберігається в localStorage.
 * Для ePrivacy/GDPR і ЗУ «Про захист персональних даних» cookie і localStorage
 * рівнозначні: згода потрібна для всього, що не є строго необхідним для роботи сервісу.
 *
 * Аналітики на сайті зараз немає. Гейт написано заздалегідь, щоб при її
 * підключенні трекери фізично не могли стартувати без згоди користувача:
 * єдина дозволена точка запуску — hasAnalyticsConsent().
 */

export type ConsentLevel = 'necessary' | 'all';

/** Збережений вибір. Старе значення-рядок читається як { level, version: null, ts: null }. */
export interface StoredConsent {
  level: ConsentLevel;
  version: string | null;
  ts: string | null;
}

const STORAGE_KEY = 'cookie_consent';
const CHANGE_EVENT = 'consent:change';
const OPEN_EVENT = 'consent:open';

// Поточна версія документів: її реєструє банер після отримання публічних налаштувань.
// Так setConsent(level) без другого аргументу (CookieSettings) теж пише версію.
let currentVersion = '';
let currentReconsentRequired = false;

export function registerLegalVersion(version: string | null | undefined, reconsentRequired = false): void {
  const next = version ?? '';
  const changed = next !== currentVersion || reconsentRequired !== currentReconsentRequired;
  currentVersion = next;
  currentReconsentRequired = reconsentRequired;
  // hasAnalyticsConsent() залежить від версії: підписники (завантажувач аналітики) мають перерахувати стан.
  if (changed && typeof window !== 'undefined') window.dispatchEvent(new Event(CHANGE_EVENT));
}

// localStorage кидает исключение в приватном режиме и при отключённом хранилище.
// Отсутствие возможности сохранить выбор не должно ронять страницу.
function safeRead(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function safeWrite(value: string | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, value);
    }
  } catch {
    return;
  }
}

const isLevel = (v: unknown): v is ConsentLevel => v === 'all' || v === 'necessary';

/** Безпечний розбір сирого значення; пошкоджене значення -> null (як при першому візиті). */
export function parseConsent(raw: string | null): StoredConsent | null {
  if (raw === null) return null;
  if (isLevel(raw)) return { level: raw, version: null, ts: null };
  try {
    const obj: unknown = JSON.parse(raw);
    if (obj && typeof obj === 'object' && isLevel((obj as { level?: unknown }).level)) {
      const o = obj as { level: ConsentLevel; version?: unknown; ts?: unknown };
      return {
        level: o.level,
        version: typeof o.version === 'string' ? o.version : null,
        ts: typeof o.ts === 'string' ? o.ts : null,
      };
    }
  } catch {
    return null;
  }
  return null;
}

/** Сирий рядок із сховища (примітив: стабільний знімок для useSyncExternalStore). */
export function getRawConsent(): string | null {
  if (typeof window === 'undefined') return null;
  return safeRead();
}

export function readConsent(): StoredConsent | null {
  return parseConsent(getRawConsent());
}

/** Поточний вибір користувача. null — вибір ще не зроблено. */
export function getConsent(): ConsentLevel | null {
  return readConsent()?.level ?? null;
}

export function setConsent(level: ConsentLevel, version: string | null = currentVersion || null): void {
  if (typeof window === 'undefined') return;
  const value: StoredConsent = { level, version, ts: new Date().toISOString() };
  safeWrite(JSON.stringify(value));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/**
 * Чи питати знову: тільки якщо версія змінилась І адмін вимагає повторної згоди.
 * Порожня поточна версія (не задана власником) ніколи не викликає повторного запиту.
 */
export function shouldAskAgain(
  storedVersion: string | null,
  currentVersion: string | null | undefined,
  reconsentRequired: boolean,
): boolean {
  return reconsentRequired && !!currentVersion && storedVersion !== currentVersion;
}

/** Відкрити панель вибору cookie з будь-якої сторінки (кнопка в футері). */
export function openConsentSettings(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(OPEN_EVENT));
}

export function subscribeConsentOpen(onOpen: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(OPEN_EVENT, onOpen);
  return () => window.removeEventListener(OPEN_EVENT, onOpen);
}

/** Відкликання згоди — вимога ст. 11 ЗУ «Про захист персональних даних». */
export function clearConsent(): void {
  if (typeof window === 'undefined') return;
  safeWrite(null);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/**
 * Єдина точка, через яку дозволено запускати аналітику та будь-які трекери.
 * Поки повертає false завжди, доки користувач не обрав «Прийняти всі».
 */
export function hasAnalyticsConsent(): boolean {
  const stored = readConsent();
  if (stored?.level !== 'all') return false;
  // Если по версии документов нужно спросить снова, прежняя «все» уже не действует.
  return !shouldAskAgain(stored.version, currentVersion, currentReconsentRequired);
}

/** Підписка для useSyncExternalStore. Ловить і зміну в цій вкладці, і в сусідніх. */
export function subscribeConsent(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}
