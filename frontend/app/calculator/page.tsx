'use client';
import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { pricingApi, CalcInputs } from '@/api/pricing';
import { CalcResult } from '@/lib/types';
import CalcBreakdown from '@/components/calculator/CalcBreakdown';
import DemoBanner from '@/components/ui/DemoBanner';
import Spinner from '@/components/ui/Spinner';

// Числові поля в стані форми — рядки: порожнє поле лишається порожнім (не 0), спрацьовує required.
type CalcForm = Omit<CalcInputs, 'engine_cc' | 'vehicle_year' | 'battery_capacity_kwh'> & {
  engine_cc: string;
  vehicle_year: string;
  battery_capacity_kwh: string;
};

const EV_FUELS = ['electric', 'phev'];

const DEFAULTS: CalcForm = {
  auction_price_usd: '10000',
  engine_cc: '2000',
  fuel_type: 'petrol',
  vehicle_year: '2020',
  battery_capacity_kwh: '',
  auction: 'copart',
  auction_location: 'general',
  us_port: 'houston',
  eu_port: 'klaipeda',
};

function toInputs(form: CalcForm): CalcInputs {
  const { battery_capacity_kwh, engine_cc, vehicle_year, ...rest } = form;
  return {
    ...rest,
    engine_cc: Number(engine_cc),
    vehicle_year: Number(vehicle_year),
    ...(EV_FUELS.includes(form.fuel_type) ? { battery_capacity_kwh } : {}),
  };
}

function CalculatorForm() {
  const params = useSearchParams();
  const [form, setForm] = useState<CalcForm>({
    ...DEFAULTS,
    auction_price_usd: params.get('price') ?? DEFAULTS.auction_price_usd,
    engine_cc: params.get('engine_cc') ?? DEFAULTS.engine_cc,
    fuel_type: params.get('fuel_type') ?? DEFAULTS.fuel_type,
    vehicle_year: params.get('year') ?? DEFAULTS.vehicle_year,
  });
  const [result, setResult] = useState<CalcResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const listingParam = Number(params.get('listing'));
  const listingId = Number.isInteger(listingParam) && listingParam > 0 ? listingParam : undefined;

  const set = (key: keyof CalcForm, val: string) =>
    setForm(f => ({ ...f, [key]: val }));
  const isEv = EV_FUELS.includes(form.fuel_type);

  const calculate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const r = await pricingApi.calculate(toInputs(form));
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
            <label htmlFor="auction_price_usd" className="block text-xs font-semibold text-slate-600 mb-1">Ціна аукціону ($)</label>
            <input id="auction_price_usd" name="auction_price_usd" type="number" required min={0} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.auction_price_usd} onChange={e => set('auction_price_usd', e.target.value)} />
          </div>
          <div>
            <label htmlFor="engine_cc" className="block text-xs font-semibold text-slate-600 mb-1">Об'єм двигуна (см³)</label>
            <input id="engine_cc" name="engine_cc" type="number" required min={0} max={10000} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.engine_cc} onChange={e => set('engine_cc', e.target.value)} />
          </div>
          <div>
            <label htmlFor="fuel_type" className="block text-xs font-semibold text-slate-600 mb-1">Тип палива</label>
            <select id="fuel_type" name="fuel_type" className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.fuel_type} onChange={e => set('fuel_type', e.target.value)}>
              <option value="petrol">Бензин</option>
              <option value="diesel">Дизель</option>
              <option value="electric">Електро</option>
              <option value="hybrid">Гібрид</option>
              <option value="phev">Гібрид (PHEV)</option>
            </select>
          </div>
          {isEv && (
            <div>
              <label htmlFor="battery_capacity_kwh" className="block text-xs font-semibold text-slate-600 mb-1">Ємність батареї (кВт·год)</label>
              <input id="battery_capacity_kwh" name="battery_capacity_kwh" type="number" required min={1} max={300} step="0.1"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.battery_capacity_kwh} onChange={e => set('battery_capacity_kwh', e.target.value)} />
              <p className="text-xs text-slate-500 mt-1">Акциз електро й PHEV рахується від ємності батареї.</p>
            </div>
          )}
          <div>
            <label htmlFor="vehicle_year" className="block text-xs font-semibold text-slate-600 mb-1">Рік випуску</label>
            <input id="vehicle_year" name="vehicle_year" type="number" required min={1990} max={2030} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.vehicle_year} onChange={e => set('vehicle_year', e.target.value)} />
          </div>
          <div>
            <label htmlFor="auction" className="block text-xs font-semibold text-slate-600 mb-1">Аукціон</label>
            <select id="auction" name="auction" className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.auction} onChange={e => set('auction', e.target.value)}>
              <option value="copart">Copart</option>
              <option value="iaai">IAAI</option>
            </select>
          </div>
          <div>
            <label htmlFor="us_port" className="block text-xs font-semibold text-slate-600 mb-1">Порт США</label>
            <select id="us_port" name="us_port" className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.us_port} onChange={e => set('us_port', e.target.value)}>
              <option value="houston">Houston</option>
              <option value="baltimore">Baltimore</option>
              <option value="new_jersey">New Jersey</option>
            </select>
          </div>
          <div>
            <label htmlFor="eu_port" className="block text-xs font-semibold text-slate-600 mb-1">Порт ЄС</label>
            <select id="eu_port" name="eu_port" className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              value={form.eu_port} onChange={e => set('eu_port', e.target.value)}>
              <option value="klaipeda">Клайпеда</option>
              <option value="gdansk">Гданськ</option>
            </select>
          </div>
          <div>
            <label htmlFor="auction_location" className="block text-xs font-semibold text-slate-600 mb-1">Локація аукціону</label>
            <select id="auction_location" name="auction_location" className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
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
      {result && (
        <CalcBreakdown result={result} listingId={listingId}
          onNewCalculation={() => { setResult(null); window.scrollTo({ top: 0 }); }} />
      )}
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
