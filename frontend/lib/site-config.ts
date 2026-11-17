import { serverGet } from '@/lib/server-api';
import { getSiteSettings } from '@/lib/site-settings';

/** Публічні налаштування та ліміти (задача 6.4). null — API недоступне. */
export async function getSiteConfig(revalidate = 60) {
  return getSiteSettings(revalidate);
}

/** Платна послуга просування з GET /api/v1/local/tariffs/ (без розділу — null). */
export interface PromotionTariff {
  id: number;
  code: string;
  name: string;
  type: string;
  price: string;
  currency: string;
  duration_days: number;
  description: string;
}

export async function getPromotionTariffs(revalidate = 0): Promise<PromotionTariff[] | null> {
  return serverGet<PromotionTariff[]>('/api/v1/local/tariffs/', revalidate);
}

/**
 * Чи тарифи демонстраційні (2.6): is_demo з GET /api/v1/pricing/rates/.
 * null — API недоступне; підвал і головна тоді не показують нічого зайвого.
 */
export async function getDemoStatus(revalidate = 60): Promise<boolean | null> {
  const data = await serverGet<{ is_demo?: boolean }>('/api/v1/pricing/rates/', revalidate);
  return data ? data.is_demo === true : null;
}
