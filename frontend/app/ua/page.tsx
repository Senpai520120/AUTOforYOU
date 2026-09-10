import type { Metadata } from 'next';
import { Suspense } from 'react';
import Link from 'next/link';
import LocalListingFilters from '@/components/local/LocalListingFilters';
import LocalCatalogGrid from './LocalCatalogGrid';
import SaveSearchButton from '@/components/local/SaveSearchButton';
import { buildQuery, serverGet, type SearchParams } from '@/lib/server-api';
import type { LocalListing, PaginatedResponse } from '@/lib/types';

// Каталог залежить від query-параметрів фільтрів, тому рендериться на кожен
// запит. Дані самі кешуються на рівні fetch.
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Каталог Україна',
  description:
    'Місцеві оголошення про продаж авто по всій Україні. Фільтри за маркою, регіоном, паливом, ціною.',
  openGraph: {
    title: 'Каталог Україна — AUTOforYOU',
    description: 'Купити авто в Україні: оголошення від власників і дилерів.',
    type: 'website',
  },
};

/**
 * Білий список фільтрів. Має збігатися з тим, що читає
 * local_listings/filters.py — інакше параметр мовчки не спрацює.
 */
const LOCAL_FILTERS = [
  'make', 'model', 'year_min', 'year_max', 'price_min', 'price_max',
  'fuel_type', 'transmission', 'body_type', 'region', 'city',
  'mileage_max', 'search', 'ordering', 'page',
] as const;

export default async function UaCatalogPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const data = await serverGet<PaginatedResponse<LocalListing>>(
    `/api/v1/local/listings/${buildQuery(params, LOCAL_FILTERS)}`,
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Каталог Україна</h1>
          <p className="text-sm text-slate-500 mt-1">Місцеві оголошення від власників</p>
        </div>
        <div className="flex items-center gap-2">
          <Suspense>
            <SaveSearchButton />
          </Suspense>
          <Link
            href="/local/new"
            className="bg-amber-500 hover:bg-amber-400 text-black font-semibold px-4 py-2 rounded-lg text-sm transition-colors"
          >
            + Подати оголошення
          </Link>
        </div>
      </div>

      <Suspense>
        <LocalListingFilters />
      </Suspense>

      <div className="mt-6">
        <LocalCatalogGrid data={data} params={params} />
      </div>
    </div>
  );
}
