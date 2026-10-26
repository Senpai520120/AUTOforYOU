'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRequireAuth } from '@/lib/use-require-auth';
import Link from 'next/link';
import { getSavedSearches, deleteSavedSearch, patchSavedSearch } from '@/api/saved-searches';
import LoadingState from '@/components/ui/LoadingState';
import ErrorState from '@/components/ui/ErrorState';
import EmptyState from '@/components/ui/EmptyState';
import { getErrorMessage } from '@/lib/errors';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
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
  const { user, loading } = useRequireAuth();
  const [items, setItems] = useState<SavedSearch[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<SavedSearch | null>(null);

  const load = useCallback(() => {
    setBusy(true);
    setError(null);
    getSavedSearches().then(setItems).catch(setError).finally(() => setBusy(false));
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  const confirmRemove = async () => {
    if (!toDelete) return;
    const target = toDelete;
    setActionError(null);
    try {
      await deleteSavedSearch(target.id);
      setItems(prev => prev.filter(s => s.id !== target.id));
    } catch (e) {
      setActionError(getErrorMessage(e));
    } finally {
      setToDelete(null);
    }
  };

  const toggleNotify = async (item: SavedSearch) => {
    setActionError(null);
    try {
      await patchSavedSearch(item.id, { notify: !item.notify });
      setItems(prev => prev.map(s => s.id === item.id ? { ...s, notify: !s.notify } : s));
    } catch (e) {
      setActionError(getErrorMessage(e));
    }
  };

  if (loading || !user) return <LoadingState />;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
        <Link href="/me" className="hover:text-blue-700">Кабінет</Link>
        <span>/</span>
        <span>Збережені пошуки</span>
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-4">Збережені пошуки</h1>

      {actionError && <p role="alert" className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{actionError}</p>}

      {busy ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState icon="🔍" title="Немає збережених пошуків." action={{ label: 'Перейти до каталогу →', href: '/ua' }} />
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
                    {item.notify ? '🔔 Сповіщення увімк.' : '🔕 Сповіщення вимк.'}
                  </button>
                  <button
                    onClick={() => setToDelete(item)}
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
      <ConfirmDialog
        open={toDelete !== null}
        title="Видалити збережений пошук?"
        message={toDelete?.name}
        onConfirm={confirmRemove}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
}
