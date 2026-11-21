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
      <h2 id="model-facts-title" className="mb-3 text-lg font-semibold text-foreground">Коротко про модель</h2>
      <dl className="grid grid-cols-1 gap-3 rounded-xl border border-border bg-card p-4 text-sm sm:grid-cols-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex flex-col">
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="font-semibold text-card-foreground">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
