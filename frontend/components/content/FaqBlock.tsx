import type { FaqEntry } from '@/lib/types';
import { FAQ_LABEL } from '@/lib/labels';

interface Props {
  items: FaqEntry[];
  testId?: string;
}

/**
 * FAQ на нативних <details>: працює без JS. Текст відповіді виводиться як текст React
 * (екранується), переноси рядків — через whitespace-pre-line. HTML з адмінки не інтерпретується.
 */
export default function FaqBlock({ items, testId = 'faq-block' }: Props) {
  if (items.length === 0) return null;
  return (
    <section aria-labelledby={`${testId}-title`} data-testid={testId} className="mt-10">
      <h2 id={`${testId}-title`} className="text-xl font-bold text-slate-900 mb-4">{FAQ_LABEL}</h2>
      <div className="space-y-2">
        {items.map((item, i) => (
          <details key={i} data-testid="faq-item" className="bg-white border border-slate-200 rounded-xl px-4 py-3">
            <summary className="cursor-pointer font-semibold text-slate-800">{item.question}</summary>
            <p className="mt-2 text-sm text-slate-600 whitespace-pre-line">{item.answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
