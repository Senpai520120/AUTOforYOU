import type { MetadataRoute } from 'next';
import { isC2CEnabled } from '@/lib/c2c';

export const dynamic = 'force-dynamic';

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua';

export default async function robots(): Promise<MetadataRoute.Robots> {
  const c2c = await isC2CEnabled();
  return {
    rules: {
      userAgent: '*',
      allow: ['/', '/calculator'],
      disallow: [
        '/listings',   // каталог лотів заморожено (задача 2.8)
        '/b2b',        // B2B-доска заморожена
        '/dealers',    // заявки дилерів заморожено
        '/me/',        // личный кабинет
        '/b2b/',       // B2B-доска (только дилеры)
        '/dealers/',   // заявки дилеров
        '/login',
        '/register',
        '/admin/',
        '/api/',
        // Розділ «Оголошення по Україні» закритий, поки C2C_ENABLED=false.
        ...(c2c ? [] : ['/ua', '/local/']),
      ],
    },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
