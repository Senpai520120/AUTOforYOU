'use client';
import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { pricingApi } from '@/api/pricing';
import { Calculation, PaginatedResponse } from '@/lib/types';
import Spinner from '@/components/ui/Spinner';
import Link from 'next/link';

export default function MyCalculationsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<PaginatedResponse<Calculation> | null>(null);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !user) { router.push('/login'); return; }
    if (user) {
      pricingApi.myCalculations().then(setData).finally(() => setFetching(false));
    }
  }, [user, loading, router]);

  if (loading || fetching) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/me" className="text-blue-600 hover:underline text-sm">← Кабінет</Link>
        <h1 className="text-xl font-bold text-slate-900">Мої розрахунки</h1>
      </div>

      {!data || data.results.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-400 text-lg mb-4">Розрахунків поки немає</p>
          <Link href="/calculator" className="bg-blue-700 text-white px-6 py-2 rounded-xl font-semibold hover:bg-blue-800">
            Порахувати
          </Link>
        </div>
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
