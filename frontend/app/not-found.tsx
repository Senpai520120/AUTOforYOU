import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Сторінку не знайдено',
  robots: { index: false },
};

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <p className="text-8xl font-extrabold text-link mb-4">404</p>
      <h1 className="text-2xl font-bold text-foreground mb-2">Сторінку не знайдено</h1>
      <p className="text-muted-foreground mb-8 max-w-sm">
        Можливо, посилання застаріло.
      </p>
      <Link
        href="/calculator"
        className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold px-6 py-3 rounded-xl transition-colors"
      >
        Порахувати вартість
      </Link>
      <Link href="/" className="mt-4 text-sm text-link hover:underline">
        На головну
      </Link>
    </div>
  );
}
