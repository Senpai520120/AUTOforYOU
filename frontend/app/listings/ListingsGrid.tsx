import Link from 'next/link';
import ListingCard from '@/components/listings/ListingCard';
import type { Listing, PaginatedResponse } from '@/lib/types';
import { pageHref, type SearchParams } from '@/lib/server-api';

/**
 * Серверний компонент. Раніше вантажив дані в useEffect, через що робот
 * бачив порожню сітку, а sitemap.ts при цьому серверно збирав ті самі
 * оголошення й обіцяв пошуковику їхні адреси.
 */
export default function ListingsGrid({
  data,
  params,
}: {
  data: PaginatedResponse<Listing> | null;
  params: SearchParams;
}) {
  if (data === null) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-500">Не вдалося завантажити список оголошень.</p>
        <p className="text-slate-400 text-sm mt-1">Спробуйте оновити сторінку пізніше.</p>
      </div>
    );
  }

  if (data.results.length === 0) {
    return (
      <div className="text-center py-20">
        <p className="text-5xl mb-4" aria-hidden="true">🚗</p>
        <p className="text-slate-500 text-lg">Оголошень не знайдено</p>
        <p className="text-slate-400 text-sm mt-1">Спробуйте змінити фільтри</p>
      </div>
    );
  }

  const rawPage = Array.isArray(params.page) ? params.page[0] : params.page;
  const currentPage = Number(rawPage ?? 1);

  return (
    <>
      <p className="text-sm text-slate-500 mb-4">Знайдено: {data.count}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
        {data.results.map(l => (
          <ListingCard key={l.id} listing={l} />
        ))}
      </div>

      {(data.next || data.previous) && (
        <nav aria-label="Пагінація" className="flex justify-center gap-4 mt-8">
          {data.previous && (
            <Link
              href={pageHref('/listings', params, currentPage - 1)}
              className="px-4 py-2 border border-slate-300 rounded-lg hover:border-blue-400 transition-colors text-sm"
            >
              ← Назад
            </Link>
          )}
          {data.next && (
            <Link
              href={pageHref('/listings', params, currentPage + 1)}
              className="px-4 py-2 border border-slate-300 rounded-lg hover:border-blue-400 transition-colors text-sm"
            >
              Далі →
            </Link>
          )}
        </nav>
      )}
    </>
  );
}
