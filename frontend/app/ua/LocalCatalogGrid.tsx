import Link from 'next/link';
import LocalListingCard from '@/components/local/LocalListingCard';
import type { LocalListing, PaginatedResponse } from '@/lib/types';
import { pageHref, type SearchParams } from '@/lib/server-api';

const PAGE_SIZE = 20;

/**
 * Серверний компонент. Раніше це був клієнтський грід, який вантажив дані
 * в useEffect — робот отримував порожню сітку, хоча sitemap обіцяв йому
 * сторінки з оголошеннями.
 *
 * data === null означає, що API не відповів: показуємо це окремо від
 * «нічого не знайдено», інакше збій виглядав би як порожній каталог.
 */
export default function LocalCatalogGrid({
  data,
  params,
}: {
  data: PaginatedResponse<LocalListing> | null;
  params: SearchParams;
}) {
  if (data === null) {
    return (
      <div className="text-center py-12 text-slate-500">
        Не вдалося завантажити оголошення. Спробуйте оновити сторінку пізніше.
      </div>
    );
  }

  if (data.results.length === 0) {
    return (
      <div className="text-center py-16 text-slate-400">
        <p className="text-4xl mb-3" aria-hidden="true">🚗</p>
        <p className="font-medium text-slate-600">Оголошень не знайдено</p>
        <p className="text-sm mt-1">
          Спробуйте змінити фільтри або{' '}
          <Link href="/local/new" className="text-blue-600 underline">
            додайте своє оголошення
          </Link>
        </p>
      </div>
    );
  }

  const totalPages = Math.ceil(data.count / PAGE_SIZE);
  const rawPage = Array.isArray(params.page) ? params.page[0] : params.page;
  const currentPage = Number(rawPage ?? 1);

  return (
    <div>
      <p className="text-sm text-slate-500 mb-4">Знайдено: {data.count} оголошень</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {data.results.map(l => (
          <LocalListingCard key={l.id} listing={l} />
        ))}
      </div>

      {totalPages > 1 && (
        <nav aria-label="Пагінація" className="mt-8 flex justify-center gap-2 flex-wrap">
          {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
            <Link
              key={p}
              href={pageHref('/ua', params, p)}
              aria-current={p === currentPage ? 'page' : undefined}
              className={`px-3 py-1.5 rounded text-sm border transition-colors ${
                p === currentPage
                  ? 'bg-blue-700 text-white border-blue-700'
                  : 'border-slate-200 hover:bg-slate-50 text-slate-700'
              }`}
            >
              {p}
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
}
