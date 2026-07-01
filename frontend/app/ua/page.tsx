import type { Metadata } from 'next';
import { Suspense } from 'react';
import Link from 'next/link';
import LocalListingFilters from '@/components/local/LocalListingFilters';
import LocalCatalogGrid from './LocalCatalogGrid';
import { ListingsGridSkeleton } from '@/components/ui/Skeleton';

export const metadata: Metadata = {
  title: 'Каталог Україна',
  description: 'Місцеві оголошення про продаж авто по всій Україні. Фільтри за маркою, регіоном, паливом, ціною.',
  openGraph: {
    title: 'Каталог Україна — AUTOforYOU',
    description: 'Купити авто в Україні: оголошення від власників і дилерів.',
    type: 'website',
  },
};

export default function UaCatalogPage() {
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Каталог Україна</h1>
          <p className="text-sm text-slate-500 mt-1">Місцеві оголошення від власників</p>
        </div>
        <Link
          href="/local/new"
          className="bg-amber-500 hover:bg-amber-400 text-black font-semibold px-4 py-2 rounded-lg text-sm transition-colors"
        >
          + Подати оголошення
        </Link>
      </div>
      <Suspense>
        <LocalListingFilters />
      </Suspense>
      <div className="mt-6">
        <Suspense fallback={<ListingsGridSkeleton />}>
          <LocalCatalogGrid />
        </Suspense>
      </div>
    </div>
  );
}
