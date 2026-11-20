import type { FaqEntry } from '@/lib/jsonld';

/** «Поширені запитання» про модель: нативні <details> (шукаються через «Знайти на сторінці»). Немає питань — немає блоку. */
export default function ModelFaq({ items }: { items: FaqEntry[] }) {
  if (!items.length) return null;
  return (
    <section aria-labelledby="model-faq-title" data-testid="model-faq">
      <h2 id="model-faq-title" className="text-lg font-semibold text-slate-900 mb-2">Поширені запитання</h2>
      <div className="divide-y divide-slate-200 border-y border-slate-200">
        {items.map((it, i) => (
          <details key={i} className="py-3" data-testid="model-faq-item">
            <summary className="cursor-pointer font-medium text-slate-900">{it.question}</summary>
            <p className="mt-2 text-sm text-slate-700 whitespace-pre-line">{it.answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
