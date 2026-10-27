import type { LandingCalculation } from '@/lib/types';
import { percentFromDecimal } from '@/lib/calc-errors';

const PENDING = 'уточнюється менеджером';

function usd(value: string): string {
  return `$${Number(value).toLocaleString('uk-UA', { maximumFractionDigits: 0 })}`;
}

function uah(value: string): string {
  return `${Number(value).toLocaleString('uk-UA', { maximumFractionDigits: 0 })} грн`;
}

function formatDate(iso: string | null): string {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return y && m && d ? `${d}.${m}.${y}` : iso;
}

function Row({ label, usdValue, uahValue }: { label: string; usdValue?: string; uahValue?: string }) {
  return (
    <tr className="border-b border-slate-100">
      <td className="py-2 text-slate-700 text-sm">{label}</td>
      <td className="py-2 text-right font-mono text-sm">{usdValue ? usd(usdValue) : '—'}</td>
      <td className="py-2 text-right font-mono text-sm text-slate-500">{uahValue ? uah(uahValue) : '—'}</td>
    </tr>
  );
}

function PendingRow({ label }: { label: string }) {
  return (
    <tr className="border-b border-slate-100">
      <td className="py-2 text-slate-700 text-sm">{label}</td>
      <td colSpan={2} className="py-2 text-right text-sm text-slate-500 italic">{PENDING}</td>
    </tr>
  );
}

interface Props {
  calculation: LandingCalculation;
  termText: string;
  includedText: string;
}

/** Лише відображення: усі суми та ставки прийшли з API, фронт нічого не рахує. */
export default function LandingCalc({ calculation: c, termText, includedText }: Props) {
  const b = c.breakdown;
  const r = c.applied_rates;
  return (
    <section data-testid="landing-calc" aria-labelledby="landing-calc-title"
      className="bg-white border border-slate-200 rounded-xl p-6">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h2 id="landing-calc-title" className="font-bold text-lg text-slate-900">Вартість «під ключ»</h2>
        {c.is_estimate && (
          <span data-testid="landing-estimate"
            className="text-xs font-semibold bg-amber-100 text-amber-800 rounded-full px-2 py-0.5">
            Орієнтовний розрахунок
          </span>
        )}
      </div>
      <p className="text-3xl font-extrabold text-blue-900 font-mono" data-testid="landing-total-usd">{usd(c.total_usd)}</p>
      <p className="text-sm text-slate-500 font-mono" data-testid="landing-total-uah">{uah(c.total_uah)}</p>

      {c.is_demo && (
        <p data-testid="landing-demo" className="mt-3 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
          Розрахунок виконано на тестових тарифах: цифри не остаточні.
        </p>
      )}

      <div className="overflow-x-auto mt-4">
        <table className="w-full" data-testid="landing-breakdown">
          <thead>
            <tr className="text-xs text-slate-500 uppercase">
              <th className="text-left pb-2">Стаття</th>
              <th className="text-right pb-2">USD</th>
              <th className="text-right pb-2">UAH</th>
            </tr>
          </thead>
          <tbody>
            <Row label="Ціна аукціону" usdValue={b.auction_price_usd} />
            <Row label="Аукціонний збір" usdValue={b.auction_fee_usd} />
            <Row label="Логістика США" usdValue={b.us_land_usd} />
            <Row label="Морський фрахт" usdValue={b.ocean_freight_usd} />
            <Row label="Доставка ЄС → UA" usdValue={b.eu_to_ua_usd} />
            <Row label="Акциз" uahValue={b.excise_uah} />
            <Row label={`Мито ${percentFromDecimal(r?.duty_rate)}%`} usdValue={b.duty_usd} uahValue={b.duty_uah} />
            <Row label={`ПДВ ${percentFromDecimal(r?.vat_rate)}%`} uahValue={b.vat_uah} />
            <Row label={`Пенсійний збір ${percentFromDecimal(r?.pension_fund_rate)}%`} uahValue={b.pension_fund_uah} />
            {b.ua_delivery_pending || b.ua_delivery_usd == null
              ? <PendingRow label="Доставка по Україні" />
              : <Row label="Доставка по Україні" usdValue={b.ua_delivery_usd} />}
            {b.broker_services_pending || !b.broker_services?.length
              ? <PendingRow label="Послуги брокера" />
              : b.broker_services.map((s) => <Row key={s.title} label={s.title} usdValue={s.amount_usd} />)}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-500 mt-3" data-testid="landing-rates-date">
        Ставки діють з {formatDate(c.rates_valid_from)}.
        {c.exchange_rate_date && <> Курс НБУ на {formatDate(c.exchange_rate_date)}.</>}
        {' '}Сума орієнтовна: точну вартість підтвердить брокер.
      </p>

      {termText && (
        <p className="mt-4 text-sm text-slate-800" data-testid="landing-term">
          <span className="font-semibold">Орієнтовний термін: </span>{termText}
        </p>
      )}

      {includedText && (
        <div className="mt-4" data-testid="landing-included">
          <h3 className="font-semibold text-slate-900 text-sm">Що входить у ціну</h3>
          <p className="text-sm text-slate-600 mt-1 whitespace-pre-line">{includedText}</p>
        </div>
      )}
    </section>
  );
}
