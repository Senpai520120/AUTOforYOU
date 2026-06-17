'use client';
import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { listingsApi } from '@/api/listings';
import { Listing, PaginatedResponse } from '@/lib/types';
import ListingCard from '@/components/listings/ListingCard';
import Spinner from '@/components/ui/Spinner';
import Link from 'next/link';

export default function B2BPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<PaginatedResponse<Listing> | null>(null);
  const [fetching, setFetching] = useState(true);

  const canAccess = user && (user.is_verified_dealer || user.role === 'admin');

  useEffect(() => {
    if (!loading && !user) { router.push('/login'); return; }
    if (!loading && user && !canAccess) return;
    if (user && canAccess) {
      listingsApi.b2bBoard({}).then(setData).finally(() => setFetching(false));
    } else if (!loading) {
      setFetching(false);
    }
  }, [user, loading, canAccess, router]);

  if (loading || fetching) return <div className="flex justify-center py-20"><Spinner /></div>;

  if (!canAccess) {
    return (
      <div className="max-w-xl mx-auto text-center py-24">
        <div className="text-5xl mb-4">🔒</div>
        <h1 className="text-2xl font-bold text-slate-900 mb-3">Доступ обмежено</h1>
        <p className="text-slate-500 mb-2">B2B-дошка доступна лише для верифікованих перекупників.</p>
        <p className="text-slate-400 text-sm mb-6">Зверніться до менеджера для верифікації акаунту.</p>
        <Link href="/me" className="bg-blue-700 text-white px-6 py-2 rounded-xl font-semibold hover:bg-blue-800">
          До кабінету
        </Link>
      </div>
    );
  }

  const listings = data?.results ?? [];
  const express = listings.filter(l => l.is_express_buyout);
  const regular = listings.filter(l => !l.is_express_buyout);

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">B2B-дошка</h1>
        <p className="text-slate-500 text-sm mt-1">Оптові лоти — лише для верифікованих перекупників</p>
      </div>

      {listings.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          <p className="text-lg">Оптових лотів поки немає</p>
        </div>
      ) : (
        <>
          {express.length > 0 && (
            <section className="mb-8">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">⚡</span>
                <h2 className="text-lg font-bold text-amber-700">Терміновий викуп</h2>
                <span className="bg-amber-100 text-amber-800 text-xs px-2 py-0.5 rounded font-semibold">{express.length} лот{express.length > 1 ? 'и' : ''}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {express.map(l => <ListingCard key={l.id} listing={l} />)}
              </div>
            </section>
          )}

          {regular.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold text-slate-700 mb-4">Всі оптові лоти</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {regular.map(l => <ListingCard key={l.id} listing={l} />)}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
