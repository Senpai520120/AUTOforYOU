import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Сторінку не знайдено',
  robots: { index: false },
};

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <p className="text-8xl font-extrabold text-blue-700 mb-4">404</p>
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Сторінку не знайдено</h1>
      <p className="text-slate-500 mb-8 max-w-sm">
        Можливо, посилання застаріло або оголошення вже продано.
      </p>
      <Link
        href="/listings"
        className="bg-blue-700 hover:bg-blue-800 text-white font-semibold px-6 py-3 rounded-xl transition-colors"
      >
        Переглянути каталог
      </Link>
    </div>
  );
}
