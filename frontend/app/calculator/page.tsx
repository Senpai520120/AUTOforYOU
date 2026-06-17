'use client';
import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { pricingApi, CalcInputs } from '@/api/pricing';
import { CalcResult } from '@/lib/types';
import CalcBreakdown from '@/components/calculator/CalcBreakdown';
import DemoBanner from '@/components/ui/DemoBanner';
import Spinner from '@/components/ui/Spinner';

const DEFAULTS: CalcInputs = {
  auction_price_usd: '10000',
  engine_cc: 2000,
  fuel_type: 'petrol',
  vehicle_year: 2020,
  auction: 'copart',
  auction_location: 'general',
  us_port: 'houston',
  eu_port: 'klaipeda',
};

function CalculatorForm() {
  const params = useSearchParams();
  const [form, setForm] = useState<CalcInputs>({
    ...DEFAULTS,
    auction_price_usd: params.get('price') ?? DEFAULTS.auction_price_usd,
    engine_cc: Number(params.get('engine_cc') ?? DEFAULTS.engine_cc),
    fuel_type: params.get('fuel_type') ?? DEFAULTS.fuel_type,
    vehicle_year: Number(params.get('year') ?? DEFAULTS.vehicle_year),
  });
  const [result, setResult] = useState<CalcResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const set = (key: keyof CalcInputs, val: string | number) =>
    setForm(f => ({ ...f, [key]: val }));

  const calculate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const r = await pricingApi.calculate(form);
      setResult(r);
    } catch (err: unknown) {
      const e2 = err as { data?: Record<string, unknown> };
      setError(JSON.stringify(e2?.data ?? 'Помилка розрахунку'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <form onSubmit={calculate} className="bg-white border border-slate-200 rounded-xl p-6 mt-4 space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Ціна аукціону ($)</label>
            <input type="number" required min={0} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.auction_price_usd} onChange={e => set('auction_price_usd', e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Об'єм двигуна (см³)</label>
            <input type="number" required min={0} max={10000} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.engine_cc} onChange={e => set('engine_cc', Number(e.target.value))} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Тип палива</label>
            <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.fuel_type} onChange={e => set('fuel_type', e.target.value)}>
              <option value="petrol">Бензин</option>
              <option value="diesel">Дизель</option>
              <option value="electric">Електро</option>
              <option value="hybrid">Гібрид</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Рік випуску</label>
            <input type="number" required min={1990} max={2030} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.vehicle_year} onChange={e => set('vehicle_year', Number(e.target.value))} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Аукціон</label>
            <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.auction} onChange={e => set('auction', e.target.value)}>
              <option value="copart">Copart</option>
              <option value="iaai">IAAI</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Порт США</label>
            <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.us_port} onChange={e => set('us_port', e.target.value)}>
              <option value="houston">Houston</option>
              <option value="baltimore">Baltimore</option>
              <option value="new_jersey">New Jersey</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Порт ЄС</label>
            <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.eu_port} onChange={e => set('eu_port', e.target.value)}>
              <option value="klaipeda">Клайпеда</option>
              <option value="gdansk">Гданськ</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Локація аукціону</label>
            <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.auction_location} onChange={e => set('auction_location', e.target.value)}>
              <option value="general">Загальна (East/Central)</option>
              <option value="california">Каліфорнія</option>
            </select>
          </div>
        </div>

        <button type="submit" disabled={loading}
          className="w-full bg-blue-700 hover:bg-blue-800 disabled:opacity-60 text-white font-bold py-3 rounded-xl transition-colors text-base">
          {loading ? 'Розраховую...' : 'Розрахувати'}
        </button>

        {error && <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded p-3">{error}</p>}
      </form>

      {loading && <div className="flex justify-center mt-8"><Spinner size="lg" /></div>}
      {result && <CalcBreakdown result={result} />}
    </>
  );
}

export default function CalculatorPage() {
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Калькулятор вартості «під ключ»</h1>
      <DemoBanner />
      <Suspense fallback={<div className="flex justify-center py-20"><Spinner /></div>}>
        <CalculatorForm />
      </Suspense>
    </div>
  );
}
