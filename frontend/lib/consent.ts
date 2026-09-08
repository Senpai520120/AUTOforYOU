/**
 * Згода на використання сховища браузера.
 *
 * Сайт зберігає дані в localStorage, а не в cookie. Для ePrivacy/GDPR і
 * ЗУ «Про захист персональних даних» це рівнозначно: згода потрібна для всього,
 * що не є строго необхідним для роботи сервісу.
 *
 * Аналітики на сайті зараз немає. Гейт написано заздалегідь, щоб при її
 * підключенні трекери фізично не могли стартувати без згоди користувача:
 * єдина дозволена точка запуску — hasAnalyticsConsent().
 */

export type ConsentLevel = 'necessary' | 'all';

const STORAGE_KEY = 'cookie_consent';
const CHANGE_EVENT = 'consent:change';

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

/** Поточний вибір користувача. null — вибір ще не зроблено. */
export function getConsent(): ConsentLevel | null {
  if (typeof window === 'undefined') return null;
  const raw = safeRead();
  return raw === 'all' || raw === 'necessary' ? raw : null;
}

export function setConsent(level: ConsentLevel): void {
  if (typeof window === 'undefined') return;
  safeWrite(level);
  window.dispatchEvent(new Event(CHANGE_EVENT));
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
  return getConsent() === 'all';
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
