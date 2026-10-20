'use client';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { pricingApi, CalcInputs } from '@/api/pricing';
import { CalcOption, CalcRatesResponse, CalcResult } from '@/lib/types';
import { CalcErrorView, describeCalcError } from '@/lib/calc-errors';
import { sendMetricOncePerSession } from '@/lib/metrics';
import CalcBreakdown from '@/components/calculator/CalcBreakdown';
import DemoBanner from '@/components/ui/DemoBanner';
import Spinner from '@/components/ui/Spinner';

// Числові поля в стані форми — рядки: порожнє поле лишається порожнім (не 0), спрацьовує required.
type CalcForm = Omit<CalcInputs, 'engine_cc' | 'vehicle_year' | 'battery_capacity_kwh' | 'ua_delivery_rate'> & {
  engine_cc: string;
  vehicle_year: string;
  battery_capacity_kwh: string;
  ua_delivery_rate: string;  // '' — не обрано
};

// Списків значень тут немає (09-C1): усі select'и будуються з GET /api/v1/pricing/rates/.
function pick(options: CalcOption[], wanted: string | null | undefined): string {
  if (wanted && options.some(o => o.value === wanted)) return wanted;
  return options[0]?.value ?? '';
}

// Приклад для прямого входу. Зі сторінки лота (є ?listing) ціна порожня: ціни аукціону в лота немає (09-Q3).
const EXAMPLE = { auction_price_usd: '10000', engine_cc: '2000', vehicle_year: '2020' };

function initialForm(data: CalcRatesResponse, params: URLSearchParams): CalcForm {
  const o = data.options;
  const fromListing = params.has('listing');
  const usPort = pick(o.us_ports, params.get('us_port'));
  const euChoices = o.eu_ports.filter(p => o.us_ports.find(u => u.value === usPort)?.eu_ports.includes(p.value));
  return {
    auction_price_usd: fromListing ? '' : EXAMPLE.auction_price_usd,
    engine_cc: params.get('engine_cc') ?? (fromListing ? '' : EXAMPLE.engine_cc),
    fuel_type: pick(o.fuel_types, params.get('fuel_type')),
    vehicle_year: params.get('year') ?? (fromListing ? '' : EXAMPLE.vehicle_year),
    battery_capacity_kwh: '',
    auction: pick(o.auctions, params.get('auction')),
    auction_location: pick(o.auction_locations.filter(l => l.us_ports.includes(usPort)), null),
    us_port: usPort,
    eu_port: pick(euChoices, null),
    member_type: o.defaults.member_type ?? pick(o.member_types, null),
    payment_type: o.defaults.payment_type ?? pick(o.payment_types, null),
    title_type: o.defaults.title_type ?? pick(o.title_types, null),
    ua_delivery_rate: '',
  };
}

function toInputs(form: CalcForm, requiresBattery: boolean): CalcInputs {
  const { battery_capacity_kwh, engine_cc, vehicle_year, ua_delivery_rate, ...rest } = form;
  return {
    ...rest,
    ...(ua_delivery_rate ? { ua_delivery_rate: Number(ua_delivery_rate) } : {}),
    engine_cc: Number(engine_cc),
    vehicle_year: Number(vehicle_year),
    ...(requiresBattery ? { battery_capacity_kwh } : {}),
  };
}

const inputCls = 'w-full border border-slate-300 rounded-lg px-3 py-2 text-sm';
const labelCls = 'block text-xs font-semibold text-slate-600 mb-1';

function FieldError({ name, errors }: { name: string; errors: Record<string, string> }) {
  if (!errors[name]) return null;
  return <p className="text-xs text-red-600 mt-1" data-testid={`error-${name}`}>{errors[name]}</p>;
}

function Select({ id, label, value, options, onChange, errors, disabledValues = [] }: {
  id: keyof CalcForm; label: string; value: string; options: CalcOption[];
  onChange: (v: string) => void; errors: Record<string, string>; disabledValues?: string[];
}) {
  return (
    <div>
      <label htmlFor={id} className={labelCls}>{label}</label>
      <select id={id} name={id} className={inputCls} value={value} onChange={e => onChange(e.target.value)}>
        {options.map(o => (
          <option key={o.value} value={o.value} disabled={disabledValues.includes(o.value)}>{o.label}</option>
        ))}
      </select>
      <FieldError name={id} errors={errors} />
    </div>
  );
}

function CalculatorForm({ data }: { data: CalcRatesResponse }) {
  const params = useSearchParams();
  const o = data.options;
  const [form, setForm] = useState<CalcForm>(() => initialForm(data, params));
  const [result, setResult] = useState<CalcResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<CalcErrorView | null>(null);
  const listingParam = Number(params.get('listing'));
  const listingId = Number.isInteger(listingParam) && listingParam > 0 ? listingParam : undefined;

  const set = (key: keyof CalcForm, val: string) => setForm(f => ({ ...f, [key]: val }));
  const requiresBattery = !!o.fuel_types.find(f => f.value === form.fuel_type)?.requires_battery;
  const reachableEu = o.us_ports.find(p => p.value === form.us_port)?.eu_ports ?? [];
  const reachableUs = o.auction_locations.find(l => l.value === form.auction_location)?.us_ports ?? [];
  const fieldErrors = error?.fieldErrors ?? {};

  // Місто доступне, якщо ставка з будь-якого порту ЄС або саме з обраного.
  const cities = data.ua_delivery_rates.filter(c => !c.eu_port || c.eu_port === form.eu_port);
  const cityOptions: CalcOption[] = [
    { value: '', label: 'Не обрано — уточнити в менеджера' },
    ...cities.map(c => ({ value: String(c.id), label: c.quote_on_request ? `${c.destination} (ціна за запитом)` : c.destination })),
  ];
  const cityValue = cities.some(c => String(c.id) === form.ua_delivery_rate) ? form.ua_delivery_rate : '';

  const changeUsPort = (value: string) => setForm(f => {
    const eu = o.us_ports.find(p => p.value === value)?.eu_ports ?? [];
    return { ...f, us_port: value, eu_port: eu.includes(f.eu_port) ? f.eu_port : (eu[0] ?? '') };
  });

  const calculate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await pricingApi.calculate(toInputs({ ...form, ua_delivery_rate: cityValue }, requiresBattery)));
    } catch (err: unknown) {
      setError(describeCalcError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <DemoBanner show={data.is_demo} title={data.demo_banner.title} text={data.demo_banner.text} />
      <form onSubmit={calculate} className="bg-white border border-slate-200 rounded-xl p-6 mt-4 space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="auction_price_usd" className={labelCls}>Ціна аукціону ($)</label>
            <input id="auction_price_usd" name="auction_price_usd" type="number" required min={0} className={inputCls}
              placeholder="Наприклад, 8500"
              value={form.auction_price_usd} onChange={e => set('auction_price_usd', e.target.value)} />
            <p className="text-xs text-slate-500 mt-1">Вкажіть ставку на аукціоні в USD.</p>
            <FieldError name="auction_price_usd" errors={fieldErrors} />
          </div>
          <div>
            <label htmlFor="engine_cc" className={labelCls}>Об&apos;єм двигуна (см³)</label>
            <input id="engine_cc" name="engine_cc" type="number" required min={0} max={10000} className={inputCls}
              value={form.engine_cc} onChange={e => set('engine_cc', e.target.value)} />
            <FieldError name="engine_cc" errors={fieldErrors} />
          </div>
          <Select id="fuel_type" label="Тип палива" value={form.fuel_type} options={o.fuel_types}
            onChange={v => set('fuel_type', v)} errors={fieldErrors} />
          {requiresBattery && (
            <div>
              <label htmlFor="battery_capacity_kwh" className={labelCls}>Ємність батареї (кВт·год)</label>
              <input id="battery_capacity_kwh" name="battery_capacity_kwh" type="number" required min={1} max={300} step="0.1"
                className={inputCls}
                value={form.battery_capacity_kwh} onChange={e => set('battery_capacity_kwh', e.target.value)} />
              <p className="text-xs text-slate-500 mt-1">Акциз електро й PHEV рахується від ємності батареї.</p>
              <FieldError name="battery_capacity_kwh" errors={fieldErrors} />
            </div>
          )}
          <div>
            <label htmlFor="vehicle_year" className={labelCls}>Рік випуску</label>
            <input id="vehicle_year" name="vehicle_year" type="number" required min={1990} max={2030} className={inputCls}
              value={form.vehicle_year} onChange={e => set('vehicle_year', e.target.value)} />
            <FieldError name="vehicle_year" errors={fieldErrors} />
          </div>
          <Select id="auction" label="Аукціон" value={form.auction} options={o.auctions}
            onChange={v => set('auction', v)} errors={fieldErrors} />
          <Select id="auction_location" label="Локація аукціону" value={form.auction_location} options={o.auction_locations}
            onChange={v => set('auction_location', v)} errors={fieldErrors} />
          <Select id="us_port" label="Порт США" value={form.us_port} options={o.us_ports} onChange={changeUsPort}
            errors={fieldErrors} disabledValues={o.us_ports.map(p => p.value).filter(p => !reachableUs.includes(p))} />
          <Select id="eu_port" label="Порт ЄС" value={form.eu_port} options={o.eu_ports} onChange={v => set('eu_port', v)}
            errors={fieldErrors} disabledValues={o.eu_ports.map(p => p.value).filter(p => !reachableEu.includes(p))} />
          <Select id="ua_delivery_rate" label="Доставка по Україні (місто)" value={cityValue} options={cityOptions}
            onChange={v => set('ua_delivery_rate', v)} errors={fieldErrors} />
        </div>

        {/* 09-C5: параметри тарифу аукціону — видно, з якими значеннями рахується збір */}
        <details className="text-sm">
          <summary className="cursor-pointer text-slate-600">Параметри збору аукціону</summary>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-3">
            <Select id="member_type" label="Тип учасника" value={form.member_type ?? ''} options={o.member_types}
              onChange={v => set('member_type', v)} errors={fieldErrors} />
            <Select id="payment_type" label="Тип оплати" value={form.payment_type ?? ''} options={o.payment_types}
              onChange={v => set('payment_type', v)} errors={fieldErrors} />
            <Select id="title_type" label="Тип титулу" value={form.title_type ?? ''} options={o.title_types}
              onChange={v => set('title_type', v)} errors={fieldErrors} />
          </div>
        </details>

        <button type="submit" disabled={loading}
          className="w-full bg-blue-700 hover:bg-blue-800 disabled:opacity-60 text-white font-bold py-3 rounded-xl transition-colors text-base">
          {loading ? 'Розраховую...' : 'Розрахувати'}
        </button>

        {error && (
          <div role="alert" data-testid="calc-error" className="text-red-700 text-sm bg-red-50 border border-red-200 rounded p-3">
            <p>{error.message}</p>
            {error.details.length > 0 && (
              <ul className="list-disc ml-5 mt-1 text-xs">{error.details.map(d => <li key={d}>{d}</li>)}</ul>
            )}
          </div>
        )}
      </form>

      {loading && <div className="flex justify-center mt-8"><Spinner size="lg" /></div>}
      {result && (
        <CalcBreakdown result={result} listingId={listingId}
          onNewCalculation={() => { setResult(null); window.scrollTo({ top: 0 }); }} />
      )}
    </>
  );
}

function FormSkeleton() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4" data-testid="calc-skeleton" aria-busy="true">
      {Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-14 bg-slate-100 rounded-lg animate-pulse" />)}
    </div>
  );
}

function CalculatorLoader() {
  const [data, setData] = useState<CalcRatesResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    sendMetricOncePerSession('calculator_visit');  // 8.7: візит калькулятора, раз за вкладку
    pricingApi.options().then(setData).catch(() => setFailed(true));
  }, []);

  if (failed) {
    return <p role="alert" className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3">Не вдалося завантажити калькулятор. Спробуйте пізніше.</p>;
  }
  if (!data) return <FormSkeleton />;
  if (!data.options.is_configured) {
    return (
      <p data-testid="calc-not-configured" className="mt-4 text-sm text-slate-700 bg-slate-50 border border-slate-200 rounded p-4">
        Калькулятор ще не налаштовано. Залиште заявку — брокер порахує вартість вручну.
      </p>
    );
  }
  return <CalculatorForm data={data} />;
}

export default function CalculatorPage() {
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Калькулятор вартості «під ключ»</h1>
      <Suspense fallback={<FormSkeleton />}>
        <CalculatorLoader />
      </Suspense>
    </div>
  );
}
