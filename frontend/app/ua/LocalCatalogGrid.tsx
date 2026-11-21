import Link from 'next/link';
import { CarFront, CircleAlert } from 'lucide-react';
import { ICON_STROKE } from '@/lib/utils';
import EmptyState from '@/components/ui/EmptyState';
import { countActiveFilters } from '@/lib/local-filters';
import LocalListingCard from '@/components/local/LocalListingCard';
import type { LocalListing, PaginatedResponse } from '@/lib/types';
import { listingsCount } from '@/lib/plural';
import { pageHref, pageWindow, type SearchParams } from '@/lib/server-api';

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
  page = 1,
  postingEnabled = false,
}: {
  postingEnabled?: boolean;
  /** Нормалізований номер сторінки (page.tsx). */
  page?: number;
  data: PaginatedResponse<LocalListing> | null;
  params: SearchParams;
}) {
  if (data === null) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-center text-muted-foreground">
        <CircleAlert className="size-5 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
        Не вдалося завантажити оголошення. Спробуйте оновити сторінку пізніше.
      </div>
    );
  }

  if (data.results.length === 0) {
    const filtered = countActiveFilters((k) => params[k]) > 0;
    return (
      <div data-testid="ua-empty">
        <EmptyState
          icon={<CarFront className="size-10" strokeWidth={ICON_STROKE} aria-hidden="true" />}
          title="Оголошень не знайдено"
          hint={filtered ? 'Спробуйте змінити фільтри або скинути їх.' : 'Поки що тут порожньо.'}
          action={filtered ? { label: 'Скинути фільтри', href: '/ua' } : undefined}
        />
        <p className="mt-3 text-center text-sm text-muted-foreground">
          <Link href="/calculator" className="font-medium text-primary underline underline-offset-4 hover:text-primary/80">Порахувати пригон з США</Link>
          {postingEnabled && (
            <>
              {' '}або{' '}
              <Link href="/local/new" className="font-medium text-primary underline underline-offset-4 hover:text-primary/80">
                додайте своє оголошення
              </Link>
            </>
          )}
        </p>
      </div>
    );
  }

  const totalPages = Math.ceil(data.count / PAGE_SIZE);
  const currentPage = page;

  return (
    <div>
      <p className="text-sm text-muted-foreground mb-4">Знайдено: {listingsCount(data.count)}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {data.results.map((l, i) => (
          <LocalListingCard key={l.id} listing={l} priority={i === 0} />
        ))}
      </div>

      {totalPages > 1 && (
        <nav aria-label="Пагінація" className="mt-8 flex justify-center gap-2 flex-wrap">
          {pageWindow(currentPage, totalPages).map((p, i) => p === null ? (
            <span key={`gap-${i}`} aria-hidden="true" className="inline-flex items-center px-1 text-sm text-muted-foreground">…</span>
          ) : (
            <Link
              key={p}
              href={pageHref('/ua', params, p)}
              aria-current={p === currentPage ? 'page' : undefined}
              className={`inline-flex items-center justify-center min-w-11 min-h-11 px-3 rounded-md text-sm font-medium border transition-colors ${
                p === currentPage
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border bg-card text-foreground hover:bg-secondary'
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
