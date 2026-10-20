import { notFound } from 'next/navigation';
import { serverGet } from '@/lib/server-api';
import type { SiteSettings } from '@/lib/types';

/** Публічні налаштування сайту. null — API недоступне (сторінка показує «не заповнено»). */
export async function getSiteSettings(revalidate = 300): Promise<SiteSettings | null> {
  return serverGet<SiteSettings>('/api/v1/site-settings/', revalidate);
}

export const OWNER_NOT_CONFIGURED = 'Реквізити власника ще не заповнені адміністратором';
export const NOT_FILLED = 'не заповнено';

const FORM_LABEL: Record<string, string> = { fop: 'ФОП', tov: 'ТОВ', other: '' };

/** «ФОП Іваненко І. І.» / «ТОВ «Назва»»; порожній рядок, якщо назви немає. */
export function ownerTitle(s: SiteSettings | null): string {
  if (!s?.owner_legal_name) return '';
  return [FORM_LABEL[s.owner_legal_form] ?? '', s.owner_legal_name].filter(Boolean).join(' ');
}

/** 2026-10-01 → 01.10.2026. */
export function formatDocDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return y && m && d ? `${d}.${m}.${y}` : iso;
}

/** Email для звернень щодо ПДн: privacy_email, інакше support_email. */
export function privacyContact(s: SiteSettings | null): string {
  return s?.privacy_email || s?.support_email || '';
}

/** Email для загальних звернень: support_email, інакше privacy_email. */
export function supportContact(s: SiteSettings | null): string {
  return s?.support_email || s?.privacy_email || '';
}

export type FrozenModule = 'lots_enabled' | 'b2b_enabled' | 'dealers_enabled' | 'shipments_enabled';

/** 2.8: сторінка замороженого модуля — 404, поки флаг не true (і коли API налаштувань недоступне). */
export async function requireModule(flag: FrozenModule): Promise<void> {
  const settings = await getSiteSettings(0);
  if (settings?.[flag] !== true) notFound();
}
