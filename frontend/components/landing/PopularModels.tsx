import Link from 'next/link';
import type { LandingListItem } from '@/lib/types';

interface Props {
  models: LandingListItem[] | null;
  /** Скільки моделей показати (POPULAR_LANDINGS_LIMIT з lib/landings.ts). Без ліміту — усі. */
  limit?: number;
  /** Посилання «Усі моделі» на /prigon (на головній). */
  showAll?: boolean;
  /** Заголовок секції. */
  title?: string;
  /** data-testid секції; від нього ж id заголовка (на сторінці може бути лише один блок з таким testId). */
  testId?: string;
}

/** «Популярні моделі»: спільний блок головної та /how-it-works. Порожній список або null — нічого не рендеримо. */
export default function PopularModels({ models, limit, showAll = false, title = 'Популярні моделі', testId = 'popular-models' }: Props) {
  if (!models || models.length === 0) return null;
  const shown = limit ? models.slice(0, limit) : models;
  const titleId = `${testId}-title`;
  return (
    <section className="mt-10" data-testid={testId} aria-labelledby={titleId}>
      <h2 id={titleId} className="font-semibold text-slate-900 mb-3">{title}</h2>
      <ul className="flex flex-wrap gap-2">
        {shown.map(m => (
          <li key={m.slug}>
            <Link href={`/prigon/${m.slug}`} data-testid="popular-model"
              className="inline-block text-sm bg-white border border-slate-200 rounded-full px-3 py-1 text-blue-700 hover:border-blue-400">
              {m.make} {m.model}
            </Link>
          </li>
        ))}
      </ul>
      {showAll && (
        <p className="mt-3 text-sm">
          <Link href="/prigon" data-testid="popular-models-all" className="text-blue-700 underline">Усі моделі</Link>
        </p>
      )}
    </section>
  );
}
