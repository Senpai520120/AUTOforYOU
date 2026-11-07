'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRequireAuth } from '@/lib/use-require-auth';
import { pricingApi } from '@/api/pricing';
import { Calculation, PaginatedResponse } from '@/lib/types';
import LoadingState from '@/components/ui/LoadingState';
import ErrorState from '@/components/ui/ErrorState';
import EmptyState from '@/components/ui/EmptyState';
import Link from 'next/link';

export default function MyCalculationsPage() {
  const { user, loading } = useRequireAuth();
  const [data, setData] = useState<PaginatedResponse<Calculation> | null>(null);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setFetching(true);
    setError(null);
    pricingApi.myCalculations().then(setData).catch(setError).finally(() => setFetching(false));
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (loading || !user || fetching) return <LoadingState />;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/me" className="text-blue-600 hover:underline text-sm">← Кабінет</Link>
        <h1 className="text-xl font-bold text-slate-900">Мої розрахунки</h1>
      </div>

      {error ? (
        <ErrorState error={error} onRetry={load} />
      ) : !data || data.results.length === 0 ? (
        <EmptyState title="Розрахунків поки немає" hint="Зробіть перший розрахунок у калькуляторі." action={{ label: 'Порахувати', href: '/calculator' }} />
      ) : (
        <div className="space-y-4">
          {data.results.map(c => (
            <div key={c.id} className="bg-white border border-slate-200 rounded-xl p-5">
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-xs text-slate-500">{new Date(c.created_at).toLocaleString('uk-UA')}</p>
                  <p className="font-bold text-blue-800 text-xl mt-1">
                    ${Number(c.total_usd).toLocaleString()} / {Number(c.total_uah).toLocaleString()} грн
                  </p>
                </div>
                <span className="text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded font-semibold">⚠ Орієнтовно</span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-600">
                <span>Аукціон: ${Number(c.breakdown.auction_price_usd).toLocaleString()}</span>
                <span>Фрахт: ${Number(c.breakdown.ocean_freight_usd).toLocaleString()}</span>
                <span>Мито+ПДВ: {Number(c.breakdown.customs_total_uah).toLocaleString()} грн</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
