import type { Metadata } from 'next';
import { Suspense } from 'react';
import Link from 'next/link';
import LocalListingFilters from '@/components/local/LocalListingFilters';
import LocalCatalogGrid from './LocalCatalogGrid';
import SaveSearchButton from '@/components/local/SaveSearchButton';
import { getC2CFlags } from '@/lib/c2c';
import { buildMetadata, hasFilters } from '@/lib/seo';
import { fetchPaginated, pageNumber, type SearchParams } from '@/lib/server-api';
import type { LocalListing, PaginatedResponse } from '@/lib/types';

// Каталог залежить від query-параметрів фільтрів, тому рендериться на кожен
// запит. Дані самі кешуються на рівні fetch.
export const dynamic = 'force-dynamic';

/** Canonical — базовий шлях без query; сторінки з фільтрами не індексуються (задача 6.3). */
export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}): Promise<Metadata> {
  const params = await searchParams;
  const filtered = hasFilters(params);
  let page = pageNumber(params);
  // Сторінка поза діапазоном: fetchPaginated показує першу. Тоді canonical — на першу, і noindex.
  // fetch з тим самим URL/опціями у generateMetadata і в сторінці мемоїзується в межах запиту (Next).
  let outOfRange = false;
  if (page > 1 && !filtered) {
    const resolved = await fetchPaginated<PaginatedResponse<LocalListing>>(
      '/api/v1/local/listings/', params, LOCAL_FILTERS,
    );
    if (resolved.page !== page) {
      outOfRange = true;
      page = resolved.page;
    }
  }
  return buildMetadata({
    title: 'Каталог Україна',
    description:
      'Місцеві оголошення про продаж авто по всій Україні. Фільтри за маркою, регіоном, паливом, ціною.',
    // Self-canonical для page>1: hasFilters уже не вважає page фільтром, тож
    // сторінки пагінації індексуються (sitemap веде на них), а не склеюються з першою.
    path: page > 1 ? `/ua?page=${page}` : '/ua',
    noindex: filtered || outOfRange,
  });
}

/**
 * Білий список фільтрів. Має збігатися з тим, що читає
 * local_listings/filters.py — інакше параметр мовчки не спрацює.
 */
const LOCAL_FILTERS = [
  'make', 'model', 'year_min', 'year_max', 'price_min', 'price_max',
  'fuel_type', 'transmission', 'body_type', 'region', 'city',
  'mileage_max', 'search', 'ordering', 'page',
] as const;

const NUMERIC_FILTERS = ['year_min', 'year_max', 'price_min', 'price_max', 'mileage_max'] as const;

export default async function UaCatalogPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const flags = await getC2CFlags();
  // Нечислові значення бекенд відхиляє (400): показуємо підказку замість «не вдалося завантажити».
  const badFilters = NUMERIC_FILTERS.filter((k) => {
    const raw = params[k];
    const v = Array.isArray(raw) ? raw[0] : raw;
    return v !== undefined && v !== '' && !/^\d+(\.\d+)?$/.test(v);
  });
  const { data, page } = badFilters.length > 0
    ? { data: null, page: 1 }
    : await fetchPaginated<PaginatedResponse<LocalListing>>('/api/v1/local/listings/', params, LOCAL_FILTERS);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Каталог Україна</h1>
          <p className="text-sm text-slate-500 mt-1">Місцеві оголошення від власників</p>
        </div>
        <div className="flex items-center gap-2">
          {/* «Засів»: пошуки й подача закриті (бекенд: 404 / 403) — кнопок немає ні в кого. */}
          {flags.postingEnabled && (
            <>
              <Suspense>
                <SaveSearchButton />
              </Suspense>
              <Link
                href="/local/new"
                className="bg-amber-500 hover:bg-amber-400 text-black font-semibold px-4 py-2 rounded-lg text-sm transition-colors"
              >
                + Подати оголошення
              </Link>
            </>
          )}
        </div>
      </div>

      <Suspense>
        <LocalListingFilters />
      </Suspense>

      <div className="mt-6">
        {badFilters.length > 0 ? (
          <div role="alert" className="text-center py-12 text-red-600" data-testid="ua-filter-error">
            Некоректне значення фільтра (ціна, рік або пробіг мають бути числом). Змініть фільтри та спробуйте ще раз.
          </div>
        ) : (
          <LocalCatalogGrid data={data} params={params} page={page} postingEnabled={flags.postingEnabled} />
        )}
      </div>
    </div>
  );
}
