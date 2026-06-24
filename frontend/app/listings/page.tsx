import type { Metadata } from 'next';
import { Suspense } from 'react';
import ListingFilters from '@/components/listings/ListingFilters';
import ListingsGrid from './ListingsGrid';
import { ListingsGridSkeleton } from '@/components/ui/Skeleton';

export const metadata: Metadata = {
  title: 'Каталог авто',
  description: 'Каталог автомобілів з аукціонів США Copart та IAAI. Фільтри за статусом, типом палива, ціною. В наявності та в дорозі.',
  openGraph: {
    title: 'Каталог авто — AUTOforYOU',
    description: 'Автомобілі з США: Copart, IAAI. Фільтри за ціною, паливом, статусом.',
    type: 'website',
  },
};

export default function ListingsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Каталог автомобілів</h1>
      <Suspense>
        <ListingFilters />
      </Suspense>
      <div className="mt-6">
        <Suspense fallback={<ListingsGridSkeleton />}>
          <ListingsGrid />
        </Suspense>
      </div>
    </div>
  );
}
