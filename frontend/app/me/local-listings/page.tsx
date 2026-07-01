'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { localApi } from '@/api/local';
import { LocalListing } from '@/lib/types';

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  active:   { label: 'Активне',         cls: 'bg-green-100 text-green-800' },
  pending:  { label: 'На модерації',    cls: 'bg-amber-100 text-amber-800' },
  rejected: { label: 'Відхилено',       cls: 'bg-red-100 text-red-800' },
  hidden:   { label: 'Приховане',       cls: 'bg-slate-100 text-slate-600' },
  sold:     { label: 'Продано',         cls: 'bg-blue-100 text-blue-800' },
  expired:  { label: 'Закінчилося',     cls: 'bg-slate-100 text-slate-500' },
  draft:    { label: 'Чернетка',        cls: 'bg-slate-100 text-slate-500' },
};

export default function MyLocalListingsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [listings, setListings] = useState<LocalListing[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    localApi
      .myListings()
      .then(data => setListings(data.results))
      .catch(() => {})
      .finally(() => setFetching(false));
  }, [user]);

  async function handleDelete(id: number) {
    if (!confirm('Видалити оголошення?')) return;
    try {
      await localApi.remove(id);
      setListings(prev => prev.filter(l => l.id !== id));
    } catch {
      alert('Не вдалося видалити.');
    }
  }

  if (loading || fetching) return <div className="text-center py-20 text-slate-400">Завантаження...</div>;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Мої оголошення</h1>
        <Link
          href="/local/new"
          className="bg-amber-500 hover:bg-amber-400 text-black font-semibold px-4 py-2 rounded-lg text-sm"
        >
          + Нове оголошення
        </Link>
      </div>

      {listings.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <p className="text-4xl mb-3">📋</p>
          <p className="font-medium text-slate-600">Оголошень ще немає</p>
          <Link href="/local/new" className="mt-2 inline-block text-blue-600 underline text-sm">
            Подати перше оголошення
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {listings.map(l => {
            const badge = STATUS_BADGE[l.status] ?? { label: l.status, cls: 'bg-slate-100 text-slate-500' };
            return (
              <div key={l.id} className="bg-white border border-slate-200 rounded-xl p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link href={`/local/${l.id}`} className="font-semibold text-slate-900 hover:text-blue-700">
                        {l.make} {l.model} {l.year}
                      </Link>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
                        {badge.label}
                      </span>
                    </div>
                    <p className="text-sm text-slate-500 mt-1">
                      {Number(l.price).toLocaleString('uk-UA')} {l.currency}
                      {' · '}{l.city_name}, {l.region_name}
                      {' · '}{l.mileage_km.toLocaleString()} км
                    </p>

                    {/* Причина відхилення */}
                    {l.status === 'rejected' && l.rejection_reason && (
                      <div className="mt-2 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
                        <strong>Причина відхилення:</strong> {l.rejection_reason}
                      </div>
                    )}

                    {/* Pending info */}
                    {l.status === 'pending' && (
                      <p className="mt-2 text-xs text-amber-700 bg-amber-50 rounded px-2 py-1 inline-block">
                        Очікує перевірки модератором
                      </p>
                    )}
                  </div>

                  {/* Дата */}
                  <span className="text-xs text-slate-400 whitespace-nowrap">
                    {new Date(l.created_at).toLocaleDateString('uk-UA')}
                  </span>
                </div>

                {/* Actions */}
                <div className="mt-3 flex gap-2 flex-wrap">
                  {l.status === 'rejected' ? (
                    <Link
                      href={`/local/${l.id}/edit`}
                      className="text-sm bg-blue-700 hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Редагувати і надіслати знову
                    </Link>
                  ) : (l.status === 'active' || l.status === 'pending' || l.status === 'hidden') ? (
                    <Link
                      href={`/local/${l.id}/edit`}
                      className="text-sm border border-slate-300 hover:bg-slate-50 text-slate-700 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Редагувати
                    </Link>
                  ) : null}
                  {(l.status !== 'sold' && l.status !== 'expired') && (
                    <button
                      onClick={() => handleDelete(l.id)}
                      className="text-sm border border-red-200 hover:bg-red-50 text-red-600 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Видалити
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
