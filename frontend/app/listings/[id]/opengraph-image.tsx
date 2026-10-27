import { brandCard, ITEM_CACHE, fetchPublicJson, itemCard, notFoundResponse, OG_CONTENT_TYPE, OG_SIZE } from '@/lib/og-card';
import { isModuleEnabled } from '@/lib/site-settings';
import type { Listing } from '@/lib/types';

export const alt = 'Авто з США - AUTOforYOU';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
// Не довше, ніж сама сторінка лота.
export const revalidate = 60;

/**
 * Режим фото лота (Q8): тут тільки `off` - картка без фото Copart/IAAI.
 * Режими `partner`/`auction` потребують `shareable_images` (задача 2.11), у коді його поки немає.
 */
export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id: rawId } = await params;
  if (!/^\d+(-|$)/.test(rawId)) return notFoundResponse();
  // Модуль лотів вимкнено: нічого не розкриваємо (так само, як сторінка).
  if (!(await isModuleEnabled('lots'))) return notFoundResponse();

  const res = await fetchPublicJson<Listing>(`/api/v1/listings/${parseInt(rawId, 10)}/`);
  if (res.kind === 'missing') return notFoundResponse();
  try {
    if (res.kind === 'error') return await brandCard(undefined, undefined, ITEM_CACHE);
    const l = res.data;
    const v = l.vehicle_detail;
    return await itemCard({
      title: `${v.make} ${v.model} ${v.year}`,
      price: `${Number(l.price).toLocaleString('uk-UA')} ${l.currency}`,
      label: 'Авто з США під ключ',
    });
  } catch {
    return brandCard(undefined, undefined, ITEM_CACHE);
  }
}
