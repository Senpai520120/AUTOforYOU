import { CalcResult } from '@/lib/types';
import DemoBanner from '@/components/ui/DemoBanner';
import LeadForm from '@/components/leads/LeadForm';
import LeadCta from '@/components/leads/LeadCta';
import { percentFromDecimal } from '@/lib/calc-errors';
import { ExclusionsList, FeesFreshness } from '@/components/ui/CalcNotes';
import { formatUah, formatUsd } from '@/lib/format';
import { Badge } from '@/components/shadcn/badge';
import { Info } from 'lucide-react';
import { ICON_STROKE } from '@/lib/utils';

const PENDING = 'уточнюється менеджером';

function PendingRow({ label }: { label: string }) {
  return (
    <tr className="border-b border-border">
      <td className="py-2.5 pr-3 text-card-foreground text-sm">{label}</td>
      <td colSpan={2} className="py-2.5 text-right text-sm text-muted-foreground italic">{PENDING}</td>
    </tr>
  );
}

function Row({ label, usd, uah }: { label: string; usd?: string; uah?: string }) {
  return (
    <tr className="border-b border-border">
      <td className="py-2.5 pr-3 text-card-foreground text-sm">{label}</td>
      <td className="py-2.5 text-right font-mono text-sm">{usd ? formatUsd(usd) : '—'}</td>
      <td className="py-2.5 text-right font-mono text-sm text-muted-foreground">{uah ? formatUah(uah) : '—'}</td>
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
    <div className="bg-card text-card-foreground border border-border rounded-xl shadow-sm p-6 md:p-8 mt-6" data-testid="calc-result">
      <DemoBanner show={result.is_demo} title={result.demo_banner.title} text={result.demo_banner.text} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h3 className="font-bold text-xl text-card-foreground">Деталізація вартості «під ключ»</h3>
        {result.is_estimate && (
          <Badge variant="outline" data-testid="calc-estimate-badge" className="border-warning bg-warning/15 text-foreground font-semibold">
            <Info strokeWidth={ICON_STROKE} aria-hidden="true" />
            Орієнтовно
          </Badge>
        )}
      </div>
      <div className="overflow-x-auto" data-testid="calc-breakdown-scroll">
      <table className="w-full">
        <thead>
          <tr className="text-xs text-muted-foreground uppercase tracking-wide">
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
          <tr className="border-t-2 border-primary">
            <td className="pt-4 font-bold text-primary text-lg">
              РАЗОМ
              <span className="block text-xs font-normal text-muted-foreground">
                (з митом, акцизом, ПДВ і пенсійним збором), орієнтовно
              </span>
            </td>
            <td className="pt-4 text-right font-extrabold text-primary text-2xl font-mono" data-testid="calc-total-usd">
              {formatUsd(b.total_usd_full ?? b.total_usd)}
            </td>
            <td className="pt-4 text-right font-bold text-muted-foreground text-base font-mono">
              {formatUah(b.total_uah)}
            </td>
          </tr>
        </tfoot>
      </table>
      </div>
      <LeadCta className="mt-4 w-full sm:w-auto" />
      <p className="text-xs text-foreground mt-4 bg-warning/15 border border-warning rounded-md p-2">
        #{result.calculation_id} · {result.warning}
      </p>
      <p className="text-xs text-muted-foreground mt-2" data-testid="calc-estimate-note">
        {showEstimateNote && result.estimate_note}
        {result.rates_updated_on && <> Ставки оновлено: {formatDate(result.rates_updated_on)}.</>}
        {result.exchange_rate_date && <> Курс НБУ на {formatDate(result.exchange_rate_date)}.</>}
        {result.rates_validity_date && <> Тарифи на {formatDate(result.rates_validity_date)}.</>}
      </p>
      <FeesFreshness checkedOn={result.fees_checked_on} stale={result.fees_stale} />
      <ExclusionsList items={result.exclusions} />
      <div className="mt-6">
        {result.is_estimate && (
          <p className="text-sm text-muted-foreground mb-3">Сума орієнтовна: точну вартість підтвердить брокер.</p>
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
