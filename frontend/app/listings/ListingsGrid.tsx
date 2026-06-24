'use client';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { listingsApi } from '@/api/listings';
import { Listing, PaginatedResponse } from '@/lib/types';
import ListingCard from '@/components/listings/ListingCard';
import { ListingsGridSkeleton } from '@/components/ui/Skeleton';

export default function ListingsGrid() {
  const params = useSearchParams();
  const [data, setData] = useState<PaginatedResponse<Listing> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    listingsApi.list({
      status:    params.get('status')    ?? undefined,
      fuel_type: params.get('fuel_type') ?? undefined,
      max_price: params.get('max_price') ?? undefined,
      search:    params.get('search')    ?? undefined,
      page:      Number(params.get('page') ?? 1),
    })
      .then(setData)
      .catch(() => setError('Не вдалося завантажити список'))
      .finally(() => setLoading(false));
  }, [params]);

  if (loading) return <ListingsGridSkeleton />;

  if (error) {
    return (
      <div className="text-center py-16">
        <p className="text-red-600 mb-4">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="text-blue-600 hover:underline text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
        >
          Спробувати ще раз
        </button>
      </div>
    );
  }

  if (!data || data.results.length === 0) {
    return (
      <div className="text-center py-20">
        <p className="text-5xl mb-4" aria-hidden="true">🚗</p>
        <p className="text-slate-500 text-lg">Оголошень не знайдено</p>
        <p className="text-slate-400 text-sm mt-1">Спробуйте змінити фільтри</p>
      </div>
    );
  }

  const currentPage = Number(params.get('page') ?? 1);

  return (
    <>
      <p className="text-sm text-slate-500 mb-4">Знайдено: {data.count}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
        {data.results.map(l => <ListingCard key={l.id} listing={l} />)}
      </div>
      {(data.next || data.previous) && (
        <nav aria-label="Пагінація" className="flex justify-center gap-4 mt-8">
          {data.previous && (
            <a href={`?page=${currentPage - 1}`} className="px-4 py-2 border border-slate-300 rounded-lg hover:border-blue-400 transition-colors text-sm">
              ← Назад
            </a>
          )}
          {data.next && (
            <a href={`?page=${currentPage + 1}`} className="px-4 py-2 border border-slate-300 rounded-lg hover:border-blue-400 transition-colors text-sm">
              Далі →
            </a>
          )}
        </nav>
      )}
    </>
  );
}
