/** Дата остаточного видалення акаунта для банера (1.8). */
export function formatDeletionDate(iso: string): string {
  return new Date(iso).toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export const FLASH_KEY = 'flash_message';

/** Повідомлення для наступної сторінки після повного перезавантаження (sessionStorage вкладки). */
export function setFlash(text: string) {
  try {
    window.sessionStorage.setItem(FLASH_KEY, text);
  } catch {
    // приватний режим без sessionStorage — повідомлення просто не покажемо
  }
}
