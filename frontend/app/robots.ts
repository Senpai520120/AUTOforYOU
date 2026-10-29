import type { MetadataRoute } from 'next';
import { isC2CEnabled } from '@/lib/c2c';
import { isModuleEnabled } from '@/lib/site-settings';
import { absoluteUrl } from '@/lib/site';

export const dynamic = 'force-dynamic';

export default async function robots(): Promise<MetadataRoute.Robots> {
  const [c2c, lotsOn] = await Promise.all([isC2CEnabled(), isModuleEnabled('lots')]);
  return {
    rules: {
      userAgent: '*',
      allow: ['/'],
      disallow: [
        // `/me` без `$` совпал бы по префиксу с `/media/…` (фото объявлений) — поэтому `/me$` и `/me/`.
        // `/media/` НЕ закрываем: иначе поисковик не увидит фото. То же для `/b2b`.
        '/me$',
        '/me/',        // личный кабинет
        '/b2b$',
        '/b2b/',       // B2B-доска (только дилеры)
        '/dealers/',   // заявки дилеров
        '/local/new',  // форма подачи
        '/local/*/edit',
        '/login',
        '/register',
        '/admin/',
        '/api/',
        // Каталог лотів закритий, поки LOTS_ENABLED=false (задача 2.8).
        ...(lotsOn ? [] : ['/listings']),
        // Розділ «Оголошення по Україні» закритий, поки C2C_ENABLED=false.
        ...(c2c ? [] : ['/ua', '/local/']),
      ],
    },
    sitemap: absoluteUrl('/sitemap.xml'),
  };
}
