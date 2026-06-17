import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';
import Header from '@/components/layout/Header';
import Footer from '@/components/layout/Footer';

export const metadata: Metadata = {
  title: 'AUTOforYOU — авто з США під ключ',
  description: 'Маркетплейс автомобілів з аукціонів США (Copart/IAAI). Доставка, розмитнення, калькулятор вартості.',
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
