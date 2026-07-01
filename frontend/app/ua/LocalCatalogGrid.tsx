'use client';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { localApi } from '@/api/local';
import { LocalListing, PaginatedResponse } from '@/lib/types';
import LocalListingCard from '@/components/local/LocalListingCard';
import { ListingsGridSkeleton } from '@/components/ui/Skeleton';

export default function LocalCatalogGrid() {
  const sp = useSearchParams();
  const [data, setData] = useState<PaginatedResponse<LocalListing> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    const filters = Object.fromEntries(sp.entries());
    localApi
      .list(filters)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [sp.toString()]);

  if (loading) return <ListingsGridSkeleton />;
  if (error) return (
    <div className="text-center py-12 text-slate-500">
      Помилка завантаження. <button className="text-blue-600 underline" onClick={() => window.location.reload()}>Спробувати ще раз</button>
    </div>
  );
  if (!data || data.results.length === 0) return (
    <div className="text-center py-16 text-slate-400">
      <p className="text-4xl mb-3">🚗</p>
      <p className="font-medium text-slate-600">Оголошень не знайдено</p>
      <p className="text-sm mt-1">Спробуйте змінити фільтри або <a href="/local/new" className="text-blue-600 underline">додайте своє оголошення</a></p>
    </div>
  );

  const totalPages = Math.ceil(data.count / 20);
  const currentPage = Number(sp.get('page') ?? 1);

  return (
    <div>
      <p className="text-sm text-slate-500 mb-4">Знайдено: {data.count} оголошень</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {data.results.map(l => <LocalListingCard key={l.id} listing={l} />)}
      </div>
      {totalPages > 1 && (
        <nav aria-label="Пагінація" className="mt-8 flex justify-center gap-2">
          {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => {
            const params = new URLSearchParams(sp.toString());
            params.set('page', String(p));
            return (
              <a
                key={p}
                href={`/ua?${params.toString()}`}
                className={`px-3 py-1.5 rounded text-sm border transition-colors ${p === currentPage ? 'bg-blue-700 text-white border-blue-700' : 'border-slate-200 hover:bg-slate-50 text-slate-700'}`}
              >
                {p}
              </a>
            );
          })}
        </nav>
      )}
    </div>
  );
}
