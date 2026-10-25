import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';
import Header from '@/components/layout/Header';
import Footer from '@/components/layout/Footer';
import CookieBanner from '@/components/ui/CookieBanner';
import AttributionCapture from '@/components/layout/AttributionCapture';
import FlashMessage from '@/components/ui/FlashMessage';
import { C2CProvider } from '@/components/c2c/C2CProvider';
import { getC2CFlags } from '@/lib/c2c';

// Шапка/меню залежать від прапорців C2C (задача 6.7): рендер на кожен запит,
// інакше під час збірки (backend недоступний) запечеться «розділ закрито».
export const dynamic = 'force-dynamic';

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua';

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
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
  const c2c = await getC2CFlags();
  return (
    <html lang="uk" className="h-full">
      <body className="min-h-full flex flex-col bg-slate-50 antialiased">
        <AuthProvider>
          <C2CProvider flags={c2c}>
          <AttributionCapture />
          <Header />
          <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-8">
            <FlashMessage />
            {children}
          </main>
          <Footer />
          <CookieBanner />
          </C2CProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
