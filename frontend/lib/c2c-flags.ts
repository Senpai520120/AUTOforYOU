// Клієнтобезпечна частина (без серверних імпортів): C2CProvider — клієнтський компонент, задача 7.3.
/** Прапорці розділу «Оголошення по Україні» (задача 6.7). */
export interface C2CFlags {
  /** Розділ видно (каталог, картка, телефон авторизованому). */
  enabled: boolean;
  /** Подача відкрита всім. false при enabled=true = режим «засів». */
  postingEnabled: boolean;
  /** Створення оплат (просування) відкрите. */
  paymentsEnabled: boolean;
  /**
   * Переписка, угоди, обране/скарги по C2C, збережені пошуки. Відкриті лише в повному режимі
   * (бекенд у «засіві» віддає на них 404), тому UI їх ховає за тією ж умовою.
   */
  social: boolean;
}

export const C2C_CLOSED: C2CFlags = { enabled: false, postingEnabled: false, paymentsEnabled: false, social: false };
