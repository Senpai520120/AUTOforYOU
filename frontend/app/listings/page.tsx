import type { Metadata } from 'next';
import { Suspense } from 'react';
import ListingFilters from '@/components/listings/ListingFilters';
import ListingsGrid from './ListingsGrid';
import WholesaleHint from './WholesaleHint';
import { buildMetadata, hasFilters } from '@/lib/seo';
import { buildQuery, serverGet, type SearchParams } from '@/lib/server-api';
import type { Listing, PaginatedResponse } from '@/lib/types';

export const dynamic = 'force-dynamic';

/** Canonical — базовий шлях без query; сторінки з фільтрами не індексуються (задача 6.3). */
export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}): Promise<Metadata> {
  return buildMetadata({
    title: 'Каталог авто',
    description:
      'Каталог автомобілів з аукціонів США Copart та IAAI. Фільтри за статусом, типом палива, ціною. В наявності та в дорозі.',
    path: '/listings',
    noindex: hasFilters(await searchParams),
  });
}

/** Має збігатися з _apply_filters у listings/views.py плюс search/ordering з DRF. */
const LISTING_FILTERS = [
  'status', 'fuel_type', 'max_price', 'currency', 'search', 'ordering', 'page',
] as const;

export default async function ListingsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const data = await serverGet<PaginatedResponse<Listing>>(
    `/api/v1/listings/${buildQuery(params, LISTING_FILTERS)}`,
  );

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Каталог автомобілів</h1>

      <WholesaleHint />

      <Suspense>
        <ListingFilters />
      </Suspense>

      <div className="mt-6">
        <ListingsGrid data={data} params={params} />
      </div>
    </div>
  );
}
