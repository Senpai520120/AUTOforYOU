import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';
import Header from '@/components/layout/Header';
import Footer from '@/components/layout/Footer';

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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uk" className="h-full">
      <body className="min-h-full flex flex-col bg-slate-50 antialiased">
        <AuthProvider>
          <Header />
          <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-8">
            {children}
          </main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  );
}
