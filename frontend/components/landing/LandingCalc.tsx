import type { LandingCalculation } from '@/lib/types';
import { percentFromDecimal } from '@/lib/calc-errors';
import { ExclusionsList, FeesFreshness } from '@/components/ui/CalcNotes';
import { formatUah, formatUsd } from '@/lib/format';
import { Badge } from '@/components/shadcn/badge';
import { Card, CardContent } from '@/components/shadcn/card';
import { Clock, Info, TriangleAlert } from 'lucide-react';
import { ICON_STROKE } from '@/lib/utils';

const PENDING = 'уточнюється менеджером';

// Лендінг показує цілі суми (як і раніше), формат — спільний з калькулятором (lib/format.ts).
const usd = (value: string) => formatUsd(value, 0);
const uah = (value: string) => formatUah(value, 0);

function formatDate(iso: string | null): string {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return y && m && d ? `${d}.${m}.${y}` : iso;
}

function Row({ label, usdValue, uahValue }: { label: string; usdValue?: string; uahValue?: string }) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-2.5 pr-3 text-card-foreground text-sm">{label}</td>
      <td className="py-2.5 text-right font-mono text-sm">{usdValue ? usd(usdValue) : '—'}</td>
      <td className="py-2.5 text-right font-mono text-sm text-muted-foreground">{uahValue ? uah(uahValue) : '—'}</td>
    </tr>
  );
}

function PendingRow({ label }: { label: string }) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-2.5 pr-3 text-card-foreground text-sm">{label}</td>
      <td colSpan={2} className="py-2.5 text-right text-sm text-muted-foreground italic">{PENDING}</td>
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
    <section data-testid="landing-calc" aria-labelledby="landing-calc-title">
      <Card>
      <CardContent>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <h2 id="landing-calc-title" className="font-bold text-xl text-card-foreground">Вартість «під ключ»</h2>
        {c.is_estimate && (
          <Badge variant="outline" data-testid="landing-estimate"
            className="border-warning bg-warning/15 text-foreground font-semibold">
            <Info strokeWidth={ICON_STROKE} aria-hidden="true" />
            Орієнтовний розрахунок
          </Badge>
        )}
      </div>
      <div className="rounded-lg bg-primary/5 border border-primary/20 p-4">
        <p className="text-4xl font-extrabold text-primary font-mono" data-testid="landing-total-usd">{usd(c.total_usd_full ?? c.total_usd)}</p>
        <p className="text-base text-muted-foreground font-mono mt-1" data-testid="landing-total-uah">{uah(c.total_uah)}</p>
      </div>

      {c.is_demo && (
        <p data-testid="landing-demo" className="mt-3 flex items-start gap-2 text-sm text-foreground bg-warning/15 border border-warning rounded-md p-2">
          <TriangleAlert className="size-4 mt-0.5 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
          Розрахунок виконано на тестових тарифах: цифри не остаточні.
        </p>
      )}

      <div className="overflow-x-auto mt-4">
        <table className="w-full" data-testid="landing-breakdown">
          <thead>
            <tr className="text-xs text-muted-foreground uppercase tracking-wide">
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

      <p className="text-xs text-muted-foreground mt-3" data-testid="landing-rates-date">
        Ставки діють з {formatDate(c.rates_valid_from)}.
        {c.exchange_rate_date && <> Курс НБУ на {formatDate(c.exchange_rate_date)}.</>}
        {' '}Сума орієнтовна: точну вартість підтвердить брокер.
      </p>

      <FeesFreshness checkedOn={c.fees_checked_on} stale={c.fees_stale} />
      <ExclusionsList items={c.exclusions} />

      {termText && (
        <p className="mt-4 flex items-start gap-2 text-sm text-card-foreground" data-testid="landing-term">
          <Clock className="size-4 mt-0.5 shrink-0 text-link" strokeWidth={ICON_STROKE} aria-hidden="true" />
          <span><span className="font-semibold">Орієнтовний термін: </span>{termText}</span>
        </p>
      )}

      {includedText && (
        <div className="mt-4" data-testid="landing-included">
          <h3 className="font-semibold text-card-foreground text-sm">Що входить у ціну</h3>
          <p className="text-sm text-muted-foreground mt-1 whitespace-pre-line">{includedText}</p>
        </div>
      )}
      </CardContent>
      </Card>
    </section>
  );
}
