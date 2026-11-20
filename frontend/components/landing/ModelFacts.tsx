import type { LandingDetail } from '@/lib/types';

/** «Коротко про модель»: лише заповнені дані. Усе порожнє — блоку немає. */
export default function ModelFacts({ page }: { page: LandingDetail }) {
  const years =
    page.year_from && page.year_to
      ? page.year_from === page.year_to ? String(page.year_from) : `${page.year_from}–${page.year_to}`
      : page.year_from ?? page.year_to ?? null;
  const rows: [string, string][] = [];
  if (page.generation) rows.push(['Покоління', page.generation]);
  if (years) rows.push(['Роки випуску', String(years)]);
  if (page.fuel_type) rows.push(['Паливо', page.fuel_type]);
  if (page.engine_cc) rows.push(['Об’єм двигуна', `${page.engine_cc} см³`]);
  if (page.battery_capacity_kwh) rows.push(['Ємність батареї', `${page.battery_capacity_kwh} кВт·год`]);
  if (!rows.length) return null;
  return (
    <section aria-labelledby="model-facts-title" data-testid="model-facts">
      <h2 id="model-facts-title" className="text-lg font-semibold text-slate-900 mb-2">Коротко про модель</h2>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm text-slate-700">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-slate-500">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
