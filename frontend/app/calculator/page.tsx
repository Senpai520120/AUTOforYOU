'use client';
import { trackEvent } from '@/lib/analytics';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { pricingApi, CalcInputs } from '@/api/pricing';
import { CalcOption, CalcRatesResponse, CalcResult } from '@/lib/types';
import { CalcErrorView, describeCalcError } from '@/lib/calc-errors';
import { trackCalculatorVisitOnce } from '@/lib/metrics';
import CalcBreakdown from '@/components/calculator/CalcBreakdown';
import PartnerVinLink from '@/components/calculator/PartnerVinLink';
import CalculatorFaq from '@/components/content/CalculatorFaq';
import CalculatorHowWeCount from '@/components/calculator/CalculatorHowWeCount';
import DemoBanner from '@/components/ui/DemoBanner';
import Spinner from '@/components/ui/Spinner';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Skeleton } from '@/components/shadcn/skeleton';
import { CircleAlert } from 'lucide-react';
import { ICON_STROKE } from '@/lib/utils';
import FallbackContact, { useFallbackSettings } from '@/components/ui/FallbackContact';

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

// 10.17: без query числові поля порожні (підказка — у placeholder), щоб не підсовувати чужі значення.
// Зі сторінки лота (?listing) ціна теж порожня: ціни аукціону в лота немає (09-Q3).

/** Ціна з query: число > 0 і не більше 1 000 000, інакше ігнорується (порожньо = типове значення). */
function priceFromQuery(raw: string | null): string | null {
  if (!raw || !/^\d{1,7}(\.\d{1,2})?$/.test(raw)) return null;
  const n = Number(raw);
  return n > 0 && n <= 1_000_000 ? String(n) : null;
}

function initialForm(data: CalcRatesResponse, params: URLSearchParams): CalcForm {
  const o = data.options;
  const usPort = pick(o.us_ports, params.get('us_port'));
  const euChoices = o.eu_ports.filter(p => o.us_ports.find(u => u.value === usPort)?.eu_ports.includes(p.value));
  return {
    auction_price_usd: priceFromQuery(params.get('auction_price_usd')) ?? '',
    engine_cc: params.get('engine_cc') ?? '',
    fuel_type: pick(o.fuel_types, params.get('fuel_type')),
    vehicle_year: params.get('year') ?? '',
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
    engine_cc: engine_cc === '' ? 0 : Number(engine_cc),  // порожній об'єм допустимий лише для електро/PHEV
    vehicle_year: Number(vehicle_year),
    ...(requiresBattery ? { battery_capacity_kwh } : {}),
  };
}

const FIELD_ORDER = ['auction_price_usd', 'engine_cc', 'battery_capacity_kwh', 'vehicle_year'];

/** Клієнтська перевірка обов'язкових полів: ті самі межі й тексти, що на сервері (CalculateInputSerializer). */
function validateForm(form: CalcForm, requiresBattery: boolean): Record<string, string> {
  const errors: Record<string, string> = {};
  const price = form.auction_price_usd.trim();
  if (price === '' || Number.isNaN(Number(price))) errors.auction_price_usd = 'Вкажіть ціну аукціону ($).';
  else if (Number(price) < 0) errors.auction_price_usd = "Ціна аукціону не може бути від'ємною.";
  else if (Number(price) > 99_999_999) errors.auction_price_usd = 'Ціна аукціону завелика.';

  const cc = form.engine_cc.trim();
  if (requiresBattery) {
    if (cc !== '' && (Number(cc) < 0 || Number(cc) > 10000)) errors.engine_cc = "Об'єм двигуна має бути від 0 до 10000 см³.";
    const kwh = form.battery_capacity_kwh.trim();
    if (kwh === '' || !(Number(kwh) > 0)) errors.battery_capacity_kwh = 'Вкажіть ємність батареї (кВт·год).';
    else if (Number(kwh) > 300) errors.battery_capacity_kwh = 'Ємність батареї не може перевищувати 300 кВт·год.';
  } else if (cc === '' || !(Number(cc) >= 1)) {
    errors.engine_cc = "Вкажіть об'єм двигуна (см³).";
  } else if (Number(cc) > 10000) {
    errors.engine_cc = "Об'єм двигуна не може перевищувати 10000 см³.";
  }

  const year = form.vehicle_year.trim();
  if (year === '') errors.vehicle_year = 'Вкажіть рік випуску.';
  else if (!(Number(year) >= 1990 && Number(year) <= 2030)) errors.vehicle_year = 'Рік випуску має бути від 1990 до 2030.';
  return errors;
}

function focusFirstInvalid(errors: Record<string, string>) {
  const first = FIELD_ORDER.find(name => errors[name]) ?? Object.keys(errors)[0];
  if (first) document.getElementById(first)?.focus();
}

// Нативний <select>: e2e та мобільні браузери працюють з ним краще, ніж з Radix-списком; вигляд — як у shadcn Input.
const selectCls = 'min-h-11 w-full rounded-md border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring aria-invalid:border-destructive';
const labelCls = 'mb-1.5 text-sm font-semibold text-foreground';
const hintCls = 'text-xs text-muted-foreground mt-1.5';

function FieldError({ name, errors }: { name: string; errors: Record<string, string> }) {
  if (!errors[name]) return null;
  return <p id={`err-${name}`} role="alert" className="mt-1.5 flex items-start gap-1 text-xs font-medium text-destructive" data-testid={`error-${name}`}><CircleAlert className="mt-px size-3.5 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />{errors[name]}</p>;
}

function Select({ id, label, value, options, onChange, errors, disabledValues = [] }: {
  id: keyof CalcForm; label: string; value: string; options: CalcOption[];
  onChange: (v: string) => void; errors: Record<string, string>; disabledValues?: string[];
}) {
  return (
    <div>
      <Label htmlFor={id} className={labelCls}>{label}</Label>
      <select id={id} name={id} aria-invalid={!!errors[id]} aria-describedby={errors[id] ? `err-${id}` : undefined} className={selectCls} value={value} onChange={e => onChange(e.target.value)}>
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
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const showContact = !!error?.showContact;
  const contactSettings = useFallbackSettings(showContact);
  const listingParam = Number(params.get('listing'));
  const listingId = Number.isInteger(listingParam) && listingParam > 0 ? listingParam : undefined;

  const set = (key: keyof CalcForm, val: string) => {
    setForm(f => ({ ...f, [key]: val }));
    setClientErrors(prev => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };
  const requiresBattery = !!o.fuel_types.find(f => f.value === form.fuel_type)?.requires_battery;
  const reachableEu = o.us_ports.find(p => p.value === form.us_port)?.eu_ports ?? [];
  const reachableUs = o.auction_locations.find(l => l.value === form.auction_location)?.us_ports ?? [];
  const fieldErrors = Object.keys(clientErrors).length ? clientErrors : (error?.fieldErrors ?? {});

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
    setError(null);
    setResult(null);
    const problems = validateForm(form, requiresBattery);
    setClientErrors(problems);
    if (Object.keys(problems).length) {
      focusFirstInvalid(problems);
      return;
    }
    setLoading(true);
    try {
      setResult(await pricingApi.calculate(toInputs({ ...form, ua_delivery_rate: cityValue }, requiresBattery)));
      trackEvent('calculator_calculate', { source: 'calculator' });
    } catch (err: unknown) {
      const view = describeCalcError(err);
      setError(view);
      if (Object.keys(view.fieldErrors).length) setTimeout(() => focusFirstInvalid(view.fieldErrors), 0);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <DemoBanner show={data.is_demo} title={data.demo_banner.title} text={data.demo_banner.text} />
      <form onSubmit={calculate} noValidate className="bg-card text-card-foreground border border-border rounded-xl shadow-sm p-6 md:p-8 mt-6 space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <Label htmlFor="auction_price_usd" className={labelCls}>Ціна аукціону ($)</Label>
            <Input id="auction_price_usd" name="auction_price_usd" aria-invalid={!!fieldErrors.auction_price_usd} aria-describedby={fieldErrors.auction_price_usd ? "err-auction_price_usd" : undefined} type="number" required min={0}
              placeholder="Наприклад, 8500"
              value={form.auction_price_usd} onChange={e => set('auction_price_usd', e.target.value)} />
            <p className={hintCls}>Вкажіть ставку на аукціоні в USD.</p>
            <FieldError name="auction_price_usd" errors={fieldErrors} />
          </div>
          <div>
            <Label htmlFor="engine_cc" className={labelCls}>Об&apos;єм двигуна (см³)</Label>
            <Input id="engine_cc" name="engine_cc" aria-invalid={!!fieldErrors.engine_cc} aria-describedby={fieldErrors.engine_cc ? "err-engine_cc" : undefined} type="number" required={!requiresBattery} min={0} max={10000}
              placeholder="Наприклад, 2000"
              value={form.engine_cc} onChange={e => set('engine_cc', e.target.value)} />
            <FieldError name="engine_cc" errors={fieldErrors} />
          </div>
          <Select id="fuel_type" label="Тип палива" value={form.fuel_type} options={o.fuel_types}
            onChange={v => set('fuel_type', v)} errors={fieldErrors} />
          {requiresBattery && (
            <div>
              <Label htmlFor="battery_capacity_kwh" className={labelCls}>Ємність батареї (кВт·год)</Label>
              <Input id="battery_capacity_kwh" name="battery_capacity_kwh" aria-invalid={!!fieldErrors.battery_capacity_kwh} aria-describedby={fieldErrors.battery_capacity_kwh ? "err-battery_capacity_kwh" : undefined} type="number" required min={1} max={300} step="0.1"
               
                value={form.battery_capacity_kwh} onChange={e => set('battery_capacity_kwh', e.target.value)} />
              <p className={hintCls}>Акциз електро й PHEV рахується від ємності батареї.</p>
              <FieldError name="battery_capacity_kwh" errors={fieldErrors} />
            </div>
          )}
          <div>
            <Label htmlFor="vehicle_year" className={labelCls}>Рік випуску</Label>
            <Input id="vehicle_year" name="vehicle_year" aria-invalid={!!fieldErrors.vehicle_year} aria-describedby={fieldErrors.vehicle_year ? "err-vehicle_year" : undefined} type="number" required min={1990} max={2030}
              placeholder="Наприклад, 2019"
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
          <summary className="cursor-pointer font-medium text-muted-foreground hover:text-foreground">Параметри збору аукціону</summary>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-3">
            <Select id="member_type" label="Тип учасника" value={form.member_type ?? ''} options={o.member_types}
              onChange={v => set('member_type', v)} errors={fieldErrors} />
            <Select id="payment_type" label="Тип оплати" value={form.payment_type ?? ''} options={o.payment_types}
              onChange={v => set('payment_type', v)} errors={fieldErrors} />
            <Select id="title_type" label="Тип титулу" value={form.title_type ?? ''} options={o.title_types}
              onChange={v => set('title_type', v)} errors={fieldErrors} />
          </div>
        </details>

        <Button type="submit" size="lg" disabled={loading} className="w-full text-base font-bold">
          {loading ? 'Розраховую...' : 'Розрахувати'}
        </Button>

        {error && (
          <div role="alert" data-testid="calc-error" className="text-destructive text-sm bg-destructive/10 border border-destructive/30 rounded-md p-3">
            <p>{error.message}</p>
            {error.details.length > 0 && (
              <ul className="list-disc ml-5 mt-1 text-xs">{error.details.map(d => <li key={d}>{d}</li>)}</ul>
            )}
            {showContact && <FallbackContact settings={contactSettings} />}
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
    <div className="bg-card border border-border rounded-xl shadow-sm p-6 md:p-8 mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4" data-testid="calc-skeleton" aria-busy="true">
      {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-md bg-muted" />)}
    </div>
  );
}

function CalculatorLoader() {
  const [data, setData] = useState<CalcRatesResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    let alive = true;
    pricingApi.options()
      .then((d) => { if (alive) { setData(d); setFailed(false); } })
      .catch(() => { if (alive) setFailed(true); })
      .finally(() => { if (alive) setRetrying(false); });
    return () => { alive = false; };
  }, [attempt]);

  const notConfigured = !!data && !data.options.is_configured;
  const settings = useFallbackSettings(failed || notConfigured);
  const retry = () => {
    if (retrying) return;
    setRetrying(true);
    setAttempt((n) => n + 1);
  };

  if (failed) {
    return (
      <div role="alert" data-testid="calc-load-failed" className="mt-6 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-md p-4">
        <p>Не вдалося завантажити калькулятор.</p>
        <FallbackContact settings={settings} onRetry={retry} retrying={retrying} />
      </div>
    );
  }
  if (!data) return <FormSkeleton />;
  if (!data.options.is_configured) {
    return (
      <div data-testid="calc-not-configured" className="mt-6 text-sm text-card-foreground bg-muted border border-border rounded-md p-4">
        <p>Калькулятор ще не налаштовано. Розрахунок можна отримати в менеджера.</p>
        <FallbackContact settings={settings} onRetry={retry} retrying={retrying} />
      </div>
    );
  }
  return <CalculatorForm data={data} />;
}

export default function CalculatorPage() {
  useEffect(() => { trackCalculatorVisitOnce(); }, []);
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-balance text-2xl md:text-3xl font-extrabold tracking-tight text-foreground mb-2">Калькулятор вартості «під ключ»</h1>
      <Suspense fallback={<FormSkeleton />}>
        <CalculatorLoader />
      </Suspense>
      <PartnerVinLink />
      <CalculatorHowWeCount />
      <CalculatorFaq />
    </div>
  );
}
