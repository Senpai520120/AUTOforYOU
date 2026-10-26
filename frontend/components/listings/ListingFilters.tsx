'use client';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

export default function ListingFilters() {
  const router = useRouter();
  const params = useSearchParams();

  const update = useCallback((key: string, value: string) => {
    const p = new URLSearchParams(params.toString());
    if (value) p.set(key, value); else p.delete(key);
    p.delete('page');
    router.push(`/listings?${p.toString()}`);
  }, [params, router]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-wrap gap-3 items-end">
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1">Статус</label>
        <select
          className="border border-slate-300 rounded px-2 py-1.5 text-sm"
          value={params.get('status') ?? ''}
          onChange={e => update('status', e.target.value)}
        >
          <option value="">Усі</option>
          <option value="in_transit">У дорозі</option>
          <option value="in_stock">В наявності</option>
          <option value="sold">Продано</option>
        </select>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1">Паливо</label>
        <select
          className="border border-slate-300 rounded px-2 py-1.5 text-sm"
          value={params.get('fuel_type') ?? ''}
          onChange={e => update('fuel_type', e.target.value)}
        >
          <option value="">Усі</option>
          <option value="petrol">Бензин</option>
          <option value="diesel">Дизель</option>
          <option value="electric">Електро</option>
          <option value="hybrid">Гібрид</option>
        </select>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1">Макс. ціна ($)</label>
        <input
          type="number"
          className="border border-slate-300 rounded px-2 py-1.5 text-sm w-28"
          placeholder="без обмежень"
          defaultValue={params.get('max_price') ?? ''}
          onBlur={e => update('max_price', e.target.value)}
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1">Пошук</label>
        <input
          type="text"
          className="border border-slate-300 rounded px-2 py-1.5 text-sm w-44"
          placeholder="марка, модель, VIN"
          defaultValue={params.get('search') ?? ''}
          onBlur={e => update('search', e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') update('search', (e.target as HTMLInputElement).value); }}
        />
      </div>
    </div>
  );
}
