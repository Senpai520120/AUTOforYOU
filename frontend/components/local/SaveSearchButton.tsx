'use client';
import { useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { createSavedSearch } from '@/api/saved-searches';

export default function SaveSearchButton() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [notify, setNotify] = useState(true);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  const hasFilters = Array.from(searchParams.keys()).some(k => k !== 'page');

  if (!hasFilters) return null;

  const handleOpen = () => {
    if (!user) { router.push('/login'); return; }
    // Auto-suggest name from active filters
    const make = searchParams.get('make') ?? '';
    const model = searchParams.get('model') ?? '';
    const yearMin = searchParams.get('year_min') ?? '';
    const parts = [make, model, yearMin ? `від ${yearMin}` : ''].filter(Boolean);
    setName(parts.join(' ') || 'Мій пошук');
    setDone(false);
    setError('');
    setOpen(true);
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError('');
    const filters: Record<string, string> = {};
    searchParams.forEach((value, key) => {
      if (key !== 'page') filters[key] = value;
    });
    try {
      await createSavedSearch(name.trim(), filters, notify);
      setDone(true);
      setTimeout(() => setOpen(false), 1500);
    } catch {
      setError('Не вдалось зберегти. Спробуйте ще раз.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button
        onClick={handleOpen}
        className="text-xs border border-blue-300 text-blue-700 hover:bg-blue-50 px-3 py-1.5 rounded-lg transition-colors"
      >
        🔍 Зберегти пошук
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            {done ? (
              <div className="text-center py-4">
                <div className="text-4xl mb-2">✅</div>
                <p className="font-semibold text-slate-900">Пошук збережено!</p>
                <p className="text-xs text-slate-500 mt-1">Перегляньте у «Збережені пошуки»</p>
              </div>
            ) : (
              <>
                <h2 className="text-lg font-bold text-slate-900 mb-3">Зберегти пошук</h2>
                {error && (
                  <div className="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{error}</div>
                )}
                <label className="block text-sm text-slate-700 mb-1">Назва</label>
                <input
                  value={name}
                  onChange={e => setName(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                  autoFocus
                />
                <label className="flex items-center gap-2 mt-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={notify}
                    onChange={e => setNotify(e.target.checked)}
                    className="rounded"
                  />
                  <span className="text-sm text-slate-700">Отримувати сповіщення про нові авто</span>
                </label>
                <p className="text-xs text-slate-400 mt-1 ml-6">Раз на день, якщо з&apos;являться нові оголошення</p>
                <div className="flex gap-2 mt-4">
                  <button
                    onClick={() => setOpen(false)}
                    className="flex-1 border border-slate-300 text-slate-600 hover:border-slate-400 py-2 rounded-xl text-sm transition-colors"
                  >
                    Скасувати
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={!name.trim() || saving}
                    className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-semibold py-2 rounded-xl text-sm transition-colors"
                  >
                    {saving ? 'Збереження…' : 'Зберегти'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
