'use client';
import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getSavedSearches, deleteSavedSearch, patchSavedSearch } from '@/api/saved-searches';
import type { SavedSearch } from '@/lib/types';

function filtersLabel(filters: Record<string, string>) {
  const parts: string[] = [];
  if (filters.make) parts.push(filters.make);
  if (filters.model) parts.push(filters.model);
  if (filters.year_min || filters.year_max) {
    parts.push(`${filters.year_min ?? ''}–${filters.year_max ?? ''} р.`);
  }
  if (filters.price_min || filters.price_max) {
    parts.push(`${filters.price_min ?? ''}–${filters.price_max ?? ''} грн`);
  }
  if (filters.fuel_type) parts.push(filters.fuel_type);
  return parts.join(', ') || 'Всі оголошення';
}

export default function SavedSearchesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<SavedSearch[]>([]);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    getSavedSearches().then(setItems).catch(() => {}).finally(() => setBusy(false));
  }, [user]);

  const remove = async (id: number) => {
    await deleteSavedSearch(id).catch(() => {});
    setItems(prev => prev.filter(s => s.id !== id));
  };

  const toggleNotify = async (item: SavedSearch) => {
    await patchSavedSearch(item.id, { notify: !item.notify }).catch(() => {});
    setItems(prev => prev.map(s => s.id === item.id ? { ...s, notify: !s.notify } : s));
  };

  if (loading || !user) return null;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
        <Link href="/me" className="hover:text-blue-700">Кабінет</Link>
        <span>/</span>
        <span>Збережені пошуки</span>
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-4">Збережені пошуки</h1>

      {busy ? (
        <div className="text-slate-400 text-sm">Завантаження…</div>
      ) : items.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-slate-400">
          <div className="text-4xl mb-2">🔍</div>
          <p className="text-sm">Немає збережених пошуків.</p>
          <Link href="/ua" className="mt-3 inline-block text-blue-600 hover:underline text-sm">
            Перейти до каталогу →
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map(item => (
            <li key={item.id} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-900 text-sm">{item.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5 truncate">{filtersLabel(item.filters)}</div>
                  {item.last_notified_at && (
                    <div className="text-xs text-slate-400 mt-0.5">
                      Останній алерт: {new Date(item.last_notified_at).toLocaleDateString('uk-UA')}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <button
                    onClick={() => toggleNotify(item)}
                    title={item.notify ? 'Вимкнути алерти' : 'Увімкнути алерти'}
                    className={`text-xs px-2 py-1 rounded-lg border transition-colors ${
                      item.notify
                        ? 'border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100'
                        : 'border-slate-200 text-slate-400 hover:border-slate-300'
                    }`}
                  >
                    {item.notify ? '🔔 Алерти вкл.' : '🔕 Алерти вимк.'}
                  </button>
                  <button
                    onClick={() => remove(item.id)}
                    className="text-xs text-slate-400 hover:text-red-500 transition-colors"
                  >
                    Видалити
                  </button>
                </div>
              </div>
              <div className="mt-2">
                <Link
                  href={`/ua?${new URLSearchParams(item.filters).toString()}`}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Відкрити пошук →
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
