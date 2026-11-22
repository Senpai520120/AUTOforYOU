import type { Metadata } from 'next';
import { Manrope } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';
import Header from '@/components/layout/Header';
import Footer from '@/components/layout/Footer';
import CookieBanner from '@/components/ui/CookieBanner';
import AnalyticsLoader from '@/components/analytics/AnalyticsLoader';
import AttributionCapture from '@/components/layout/AttributionCapture';
import FlashMessage from '@/components/ui/FlashMessage';
import { C2CProvider } from '@/components/c2c/C2CProvider';
import { getC2CFlags } from '@/lib/c2c';
import { hasLandings } from '@/lib/landings';
import { SITE_URL } from '@/lib/config';

// Manrope (OFL): змінний шрифт, кирилиця; next/font сам підбирає fallback з size-adjust (без CLS).
const manrope = Manrope({
  subsets: ['latin', 'cyrillic'],
  display: 'swap',
  variable: '--font-manrope',
});

// Шапка/меню залежать від прапорців C2C (задача 6.7): рендер на кожен запит,
// інакше під час збірки (backend недоступний) запечеться «розділ закрито».
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'AUTOforYOU — авто з США під ключ',
    template: '%s | AUTOforYOU',
  },
  description: 'Маркетплейс автомобілів з аукціонів США (Copart/IAAI). Доставка, розмитнення, калькулятор вартості під ключ в Україну.',
  openGraph: {
    siteName: 'AUTOforYOU',
    type: 'website',
    locale: 'uk_UA',
  },
  twitter: {
    card: 'summary_large_image',
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [c2c, landings] = await Promise.all([getC2CFlags(), hasLandings()]);
  return (
    <html lang="uk" className={`${manrope.variable} h-full`}>
      <body className="min-h-full flex flex-col bg-background text-foreground antialiased">
        <AuthProvider>
          <C2CProvider flags={c2c}>
          <AttributionCapture />
          <Header hasLandings={landings} />
          <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-8">
            <FlashMessage />
            {children}
          </main>
          <Footer />
          <CookieBanner />
          <AnalyticsLoader />
          </C2CProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
