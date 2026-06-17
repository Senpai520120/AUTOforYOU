import { CalcResult } from '@/lib/types';
import DemoBanner from '@/components/ui/DemoBanner';

function Row({ label, usd, uah }: { label: string; usd?: string; uah?: string }) {
  return (
    <tr className="border-b border-slate-100">
      <td className="py-2 text-slate-700 text-sm">{label}</td>
      <td className="py-2 text-right font-mono text-sm">{usd ? `$${Number(usd).toLocaleString()}` : '—'}</td>
      <td className="py-2 text-right font-mono text-sm text-slate-500">{uah ? `${Number(uah).toLocaleString()} грн` : '—'}</td>
    </tr>
  );
}

export default function CalcBreakdown({ result }: { result: CalcResult }) {
  const b = result.breakdown;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 mt-2">
      <DemoBanner />
      <h3 className="font-bold text-lg text-slate-900 mb-4">Детализация стоимости «под ключ»</h3>
      <table className="w-full">
        <thead>
          <tr className="text-xs text-slate-500 uppercase">
            <th className="text-left pb-2">Статья</th>
            <th className="text-right pb-2">USD</th>
            <th className="text-right pb-2">UAH</th>
          </tr>
        </thead>
        <tbody>
          <Row label="Цена аукциона" usd={b.auction_price_usd} />
          <Row label="Аукционный сбор" usd={b.auction_fee_usd} />
          <Row label="Логистика США" usd={b.us_land_usd} />
          <Row label="Морской фрахт" usd={b.ocean_freight_usd} />
          <Row label="Доставка ЕС → UA" usd={b.eu_to_ua_usd} />
          <Row label={`Акциз (${b.excise_eur} EUR)`} uah={b.excise_uah} />
          <Row label="Пошлина 10%" usd={b.duty_usd} uah={b.duty_uah} />
          <Row label="НДС 20%" uah={b.vat_uah} />
          <Row label="Пенсионный сбор" uah={b.pension_fund_uah} />
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-blue-800">
            <td className="pt-3 font-bold text-blue-900 text-lg">ИТОГО</td>
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
    </div>
  );
}
