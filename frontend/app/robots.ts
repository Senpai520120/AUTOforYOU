import type { MetadataRoute } from 'next';

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: ['/', '/calculator'],
      disallow: [
        '/listings',   // 2.8: каталог лотів заморожено
        '/me/',        // личный кабинет
        '/b2b',        // B2B-доска (заморожено, 2.8)
        '/dealers',    // заявки дилеров (заморожено, 2.8)
        '/login',
        '/register',
        '/admin/',
        '/api/',
      ],
    },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
