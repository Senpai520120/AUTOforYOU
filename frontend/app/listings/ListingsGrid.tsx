'use client';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { listingsApi } from '@/api/listings';
import { Listing, PaginatedResponse } from '@/lib/types';
import ListingCard from '@/components/listings/ListingCard';
import Spinner from '@/components/ui/Spinner';

export default function ListingsGrid() {
  const params = useSearchParams();
  const [data, setData] = useState<PaginatedResponse<Listing> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    listingsApi.list({
      status: params.get('status') ?? undefined,
      fuel_type: params.get('fuel_type') ?? undefined,
      max_price: params.get('max_price') ?? undefined,
      search: params.get('search') ?? undefined,
      page: Number(params.get('page') ?? 1),
    }).then(setData).catch(() => setError('Не вдалося завантажити список')).finally(() => setLoading(false));
  }, [params]);

  if (loading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>;
  if (error) return <p className="text-red-600 text-center py-10">{error}</p>;
  if (!data || data.results.length === 0) {
    return <p className="text-slate-400 text-center py-16 text-lg">Оголошень не знайдено</p>;
  }

  return (
    <>
      <p className="text-sm text-slate-500 mb-4">Знайдено: {data.count}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
        {data.results.map(l => <ListingCard key={l.id} listing={l} />)}
      </div>
      {(data.next || data.previous) && (
        <div className="flex justify-center gap-4 mt-8">
          {data.previous && (
            <a href={`?page=${Number(params.get('page') ?? 1) - 1}`} className="px-4 py-2 border rounded">← Назад</a>
          )}
          {data.next && (
            <a href={`?page=${Number(params.get('page') ?? 1) + 1}`} className="px-4 py-2 border rounded">Далі →</a>
          )}
        </div>
      )}
    </>
  );
}
