import type { MetadataRoute } from 'next';

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua';

export default function robots(): MetadataRoute.Robots {
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
      ],
    },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
