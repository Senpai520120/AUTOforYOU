import { getSiteSettings } from '@/lib/site-settings';

export { C2C_CLOSED, type C2CFlags } from '@/lib/c2c-flags';
import { C2C_CLOSED, type C2CFlags } from '@/lib/c2c-flags';

/**
 * Прапорці з налаштувань сайту. Недоступність API = усе вимкнено (закрито за замовчуванням).
 * Короткий revalidate: ВОЛНА-2 вмикається змінною бекенда без пересборки фронта.
 */
export async function getC2CFlags(): Promise<C2CFlags> {
  const s = await getSiteSettings(30);
  if (!s || s.c2c_enabled !== true) return C2C_CLOSED;
  const postingEnabled = s.c2c_public_posting_enabled === true;
  return {
    enabled: true,
    postingEnabled,
    paymentsEnabled: s.payments_enabled === true,
    social: postingEnabled,
  };
}

export async function isC2CEnabled(): Promise<boolean> {
  return (await getC2CFlags()).enabled;
}

export async function isC2CPostingEnabled(): Promise<boolean> {
  const f = await getC2CFlags();
  return f.enabled && f.postingEnabled;
}

/** «Засів»: розділ видно, подача закрита (оголошення вносить staff). */
export async function isSeedingMode(): Promise<boolean> {
  const f = await getC2CFlags();
  return f.enabled && !f.postingEnabled;
}
