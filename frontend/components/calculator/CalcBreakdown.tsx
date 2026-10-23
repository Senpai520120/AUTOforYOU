import { CalcResult } from '@/lib/types';
import DemoBanner from '@/components/ui/DemoBanner';
import LeadForm from '@/components/leads/LeadForm';
import { percentFromDecimal } from '@/lib/calc-errors';

const PENDING = 'уточнюється менеджером';

function PendingRow({ label }: { label: string }) {
  return (
    <tr className="border-b border-slate-100">
      <td className="py-2 text-slate-700 text-sm">{label}</td>
      <td colSpan={2} className="py-2 text-right text-sm text-slate-500 italic">{PENDING}</td>
    </tr>
  );
}

function Row({ label, usd, uah }: { label: string; usd?: string; uah?: string }) {
  return (
    <tr className="border-b border-slate-100">
      <td className="py-2 text-slate-700 text-sm">{label}</td>
      <td className="py-2 text-right font-mono text-sm">{usd ? `$${Number(usd).toLocaleString()}` : '—'}</td>
      <td className="py-2 text-right font-mono text-sm text-slate-500">{uah ? `${Number(uah).toLocaleString()} грн` : '—'}</td>
    </tr>
  );
}

interface Props {
  result: CalcResult;
  listingId?: number;
  onNewCalculation?: () => void;
}

export default function CalcBreakdown({ result, listingId, onNewCalculation }: Props) {
  const b = result.breakdown;
  const r = result.applied_rates;
  // Q5: м'яка позначка — поки є демо-ставки або правило не звірене з брокером.
  const showEstimateNote = result.is_demo || !result.rules_confirmed;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 mt-2" data-testid="calc-result">
      <DemoBanner show={result.is_demo} title={result.demo_banner.title} text={result.demo_banner.text} />
      <h3 className="font-bold text-lg text-slate-900 mb-4">Деталізація вартості «під ключ»</h3>
      <table className="w-full">
        <thead>
          <tr className="text-xs text-slate-500 uppercase">
            <th className="text-left pb-2">Стаття</th>
            <th className="text-right pb-2">USD</th>
            <th className="text-right pb-2">UAH</th>
          </tr>
        </thead>
        <tbody>
          <Row label="Ціна аукціону" usd={b.auction_price_usd} />
          <Row label="Аукціонний збір" usd={b.auction_fee_usd} />
          <Row label="Логістика США" usd={b.us_land_usd} />
          <Row label="Морський фрахт" usd={b.ocean_freight_usd} />
          <Row label="Доставка ЄС → UA" usd={b.eu_to_ua_usd} />
          <Row label={`Акциз (${b.excise_eur} EUR)`} uah={b.excise_uah} />
          <Row label={`Мито ${percentFromDecimal(r?.duty_rate)}%`} usd={b.duty_usd} uah={b.duty_uah} />
          <Row label={`ПДВ ${percentFromDecimal(r?.vat_rate)}%`} uah={b.vat_uah} />
          <Row label={`Пенсійний збір ${percentFromDecimal(r?.pension_fund_rate)}%`} uah={b.pension_fund_uah} />
          {/* 2.7: після розмитнення; немає тарифу — «уточнюється менеджером», у підсумок не входить */}
          {b.ua_delivery_pending || b.ua_delivery_usd == null
            ? <PendingRow label="Доставка по Україні" />
            : <Row label="Доставка по Україні" usd={b.ua_delivery_usd} />}
          {b.broker_services_pending || !b.broker_services?.length
            ? <PendingRow label="Послуги брокера" />
            : b.broker_services.map(s => <Row key={s.title} label={s.title} usd={s.amount_usd} />)}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-blue-800">
            <td className="pt-3 font-bold text-blue-900 text-lg">РАЗОМ</td>
            <td className="pt-3 text-right font-extrabold text-blue-900 text-lg font-mono">
              ${Number(b.total_usd).toLocaleString()}
            </td>
            <td className="pt-3 text-right font-extrabold text-slate-600 text-base font-mono">
              {Number(b.total_uah).toLocaleString()} грн
            </td>
          </tr>
        </tfoot>
      </table>
      <p className="text-xs text-amber-700 mt-4 bg-amber-50 rounded p-2">
        #{result.calculation_id} · {result.warning}
      </p>
      <p className="text-xs text-slate-500 mt-2" data-testid="calc-estimate-note">
        {showEstimateNote && result.estimate_note}
        {result.rates_updated_on && <> Ставки оновлено: {formatDate(result.rates_updated_on)}.</>}
        {result.exchange_rate_date && <> Курс НБУ на {formatDate(result.exchange_rate_date)}.</>}
        {result.rates_validity_date && <> Тарифи на {formatDate(result.rates_validity_date)}.</>}
      </p>
      <div className="mt-6">
        {result.is_estimate && (
          <p className="text-sm text-slate-600 mb-3">Сума орієнтовна: точну вартість підтвердить брокер.</p>
        )}
        <LeadForm key={result.calculation_id} source="calculator" calculationId={result.calculation_id}
          listingId={listingId} onNew={onNewCalculation} />
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return y && m && d ? `${d}.${m}.${y}` : iso;
}
