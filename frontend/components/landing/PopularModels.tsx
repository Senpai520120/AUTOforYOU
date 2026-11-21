import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { LandingListItem } from '@/lib/types';
import { ICON_STROKE } from '@/lib/utils';

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
      <h2 id={titleId} className="mb-4 text-xl font-bold tracking-tight text-foreground">{title}</h2>
      <ul className="flex flex-wrap gap-2">
        {shown.map(m => (
          <li key={m.slug}>
            <Link href={`/prigon/${m.slug}`} data-testid="popular-model"
              className="inline-flex min-h-10 items-center rounded-full border border-border bg-card px-4 text-sm font-medium text-link shadow-xs transition-colors hover:border-primary hover:bg-primary/5">
              {m.make} {m.model}
            </Link>
          </li>
        ))}
      </ul>
      {showAll && (
        <p className="mt-4 text-sm">
          <Link href="/prigon" data-testid="popular-models-all"
            className="inline-flex items-center gap-1 font-medium text-link underline underline-offset-4 hover:text-link/80">
            Усі моделі
            <ArrowRight className="size-4" strokeWidth={ICON_STROKE} aria-hidden="true" />
          </Link>
        </p>
      )}
    </section>
  );
}
