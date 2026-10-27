'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRequireAuth } from '@/lib/use-require-auth';
import { meApi } from '@/api/me';
import { TrustedShop } from '@/lib/types';
import LoadingState from '@/components/ui/LoadingState';
import ErrorState from '@/components/ui/ErrorState';
import EmptyState from '@/components/ui/EmptyState';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import { getErrorMessage } from '@/lib/errors';
import Link from 'next/link';

const TYPE_LABELS: Record<string, string> = { service: 'СТО', painter: 'Маляр', parts: 'Запчастини', other: 'Інше' };

export default function TrustedShopsPage() {
  const { user, loading } = useRequireAuth();
  const [shops, setShops] = useState<TrustedShop[]>([]);
  const [fetching, setFetching] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', type: 'service', contacts: '', rating: 5, notes: '' });

  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [toDelete, setToDelete] = useState<TrustedShop | null>(null);

  const load = useCallback(() => {
    setFetching(true);
    setError(null);
    meApi.trustedShops.list().then(d => setShops(d.results)).catch(setError).finally(() => setFetching(false));
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    setSaving(true);
    try {
      const shop = await meApi.trustedShops.create(form as TrustedShop);
      setShops(s => [shop, ...s]);
      setShowForm(false);
      setForm({ name: '', type: 'service', contacts: '', rating: 5, notes: '' });
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const confirmRemove = async () => {
    if (!toDelete) return;
    const shop = toDelete;
    setActionError(null);
    try {
      await meApi.trustedShops.delete(shop.id);
      setShops(s => s.filter(x => x.id !== shop.id));
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setToDelete(null);
    }
  };

  if (loading || !user || fetching) return <LoadingState />;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Link href="/me" className="text-blue-600 hover:underline text-sm">← Кабінет</Link>
          <h1 className="text-xl font-bold text-slate-900">Мої партнери</h1>
        </div>
        <button onClick={() => setShowForm(v => !v)}
          className="bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-blue-800">
          + Додати
        </button>
      </div>

      {actionError && <p role="alert" className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{actionError}</p>}

      {showForm && (
        <form onSubmit={create} className="bg-white border border-blue-200 rounded-xl p-5 mb-5 space-y-3">
          <h2 className="font-semibold text-slate-800">Новий партнер</h2>
          <input required aria-label="Назва" placeholder="Назва" className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <div className="grid grid-cols-2 gap-3">
            <select aria-label="Тип" className="border border-slate-300 rounded px-3 py-2 text-sm"
              value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}>
              {Object.entries(TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <select aria-label="Рейтинг" className="border border-slate-300 rounded px-3 py-2 text-sm"
              value={form.rating} onChange={e => setForm(f => ({ ...f, rating: Number(e.target.value) }))}>
              {[5, 4, 3, 2, 1].map(r => <option key={r} value={r}>{'★'.repeat(r)}</option>)}
            </select>
          </div>
          <textarea aria-label="Контакти" placeholder="Контакти" className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.contacts} onChange={e => setForm(f => ({ ...f, contacts: e.target.value }))} />
          <textarea aria-label="Нотатки" placeholder="Нотатки" className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          <button type="submit" disabled={saving} className="disabled:opacity-50 bg-amber-500 hover:bg-amber-400 text-black font-bold px-6 py-2 rounded-lg text-sm">
            Зберегти
          </button>
        </form>
      )}

      {error ? (
        <ErrorState error={error} onRetry={load} />
      ) : shops.length === 0 ? (
        <EmptyState title="Партнерів поки немає" hint="Додайте СТО, маляра чи магазин запчастин, яким ви довіряєте." />
      ) : (
        <div className="space-y-3">
          {shops.map(s => (
            <div key={s.id} className="bg-white border border-slate-200 rounded-xl p-4 flex justify-between items-start">
              <div>
                <p className="font-semibold text-slate-900">{s.name}</p>
                <p className="text-xs text-slate-500">{TYPE_LABELS[s.type]} · {'★'.repeat(s.rating)}</p>
                {s.contacts && <p className="text-sm text-slate-600 mt-1">{s.contacts}</p>}
                {s.notes && <p className="text-xs text-slate-400 mt-0.5">{s.notes}</p>}
              </div>
              <button onClick={() => setToDelete(s)} className="text-red-400 hover:text-red-600 text-xs ml-4">
                Видалити
              </button>
            </div>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={toDelete !== null}
        title="Видалити партнера?"
        message={toDelete ? toDelete.name : undefined}
        onConfirm={confirmRemove}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
}
