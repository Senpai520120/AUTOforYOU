import { ChevronDown } from 'lucide-react';
import type { FaqEntry } from '@/lib/jsonld';
import { ICON_STROKE } from '@/lib/utils';

/** «Поширені запитання» про модель: нативні <details> (шукаються через «Знайти на сторінці»). Немає питань — немає блоку. */
export default function ModelFaq({ items }: { items: FaqEntry[] }) {
  if (!items.length) return null;
  return (
    <section aria-labelledby="model-faq-title" data-testid="model-faq">
      <h2 id="model-faq-title" className="mb-3 text-lg font-semibold text-foreground">Поширені запитання</h2>
      <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
        {items.map((it, i) => (
          <details key={i} className="group px-4 py-3" data-testid="model-faq-item">
            <summary className="flex min-h-6 cursor-pointer list-none items-center justify-between gap-3 font-medium text-card-foreground [&::-webkit-details-marker]:hidden">
              {it.question}
              <ChevronDown className="size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" strokeWidth={ICON_STROKE} aria-hidden="true" />
            </summary>
            <p className="mt-2 whitespace-pre-line text-sm text-muted-foreground">{it.answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
