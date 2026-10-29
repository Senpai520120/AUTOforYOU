import type { Metadata } from 'next';
import Link from 'next/link';
import EmptyState from '@/components/ui/EmptyState';
import ErrorState from '@/components/ui/ErrorState';
import FaqBlock from '@/components/content/FaqBlock';
import { getHowItWorks } from '@/lib/content';
import { getLandingList } from '@/lib/landings';
import { HOW_IT_WORKS_LABEL, HOW_IT_WORKS_SOON, CALC_COST_LABEL } from '@/lib/labels';
import { buildMetadata } from '@/lib/seo';

// Дані з API: без force-dynamic Next пререндерить порожню сторінку під час build.
export const dynamic = 'force-dynamic';

const DESCRIPTION =
  'Як відбувається пригон авто з аукціонів США: від заявки та торгів до доставки, розмитнення і видачі авто в Україні.';

export async function generateMetadata(): Promise<Metadata> {
  const data = await getHowItWorks();
  return buildMetadata({
    title: HOW_IT_WORKS_LABEL,
    description: DESCRIPTION,
    path: '/how-it-works',
    // Порожня сторінка або збій API не індексуються.
    noindex: data?.published !== true,
  });
}

export default async function HowItWorksPage() {
  const data = await getHowItWorks();
  const models = data?.published ? await getLandingList() : null;

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">{HOW_IT_WORKS_LABEL}</h1>

      {data === null && <ErrorState error={null} />}

      {data !== null && !data.published && (
        <div data-testid="how-it-works-empty">
          <EmptyState title={HOW_IT_WORKS_SOON} />
        </div>
      )}

      {data?.published && (
        <>
          <ol className="space-y-4" data-testid="import-steps">
            {data.steps.map((step, i) => (
              <li key={i} data-testid="import-step" className="bg-white border border-slate-200 rounded-xl p-5">
                <h2 className="font-semibold text-slate-900">
                  <span className="text-blue-700 mr-2">{i + 1}.</span>
                  {step.title}
                </h2>
                {step.duration && <p className="text-xs font-semibold text-slate-500 mt-1">{step.duration}</p>}
                {step.description && (
                  <p className="text-sm text-slate-600 mt-2 whitespace-pre-line">{step.description}</p>
                )}
              </li>
            ))}
          </ol>

          <FaqBlock items={data.faq} testId="faq-block" />

          {models && models.length > 0 && (
            <section className="mt-10" data-testid="popular-models" aria-labelledby="popular-models-title">
              <h2 id="popular-models-title" className="font-semibold text-slate-900 mb-3">Популярні моделі</h2>
              <ul className="flex flex-wrap gap-2">
                {models.map(m => (
                  <li key={m.slug}>
                    <Link href={`/prigon/${m.slug}`} data-testid="popular-model"
                      className="inline-block text-sm bg-white border border-slate-200 rounded-full px-3 py-1 text-blue-700 hover:border-blue-400">
                      {m.make} {m.model}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="mt-10 bg-blue-50 border border-blue-200 rounded-xl p-5 text-center">
            <Link
              href="/calculator"
              className="inline-block bg-blue-700 hover:bg-blue-800 text-white font-bold px-6 py-3 rounded-xl transition-colors"
            >
              {CALC_COST_LABEL}
            </Link>
            <p className="text-sm text-slate-600 mt-3">
              Заявку на підбір авто можна залишити одразу після розрахунку.
            </p>
          </div>

          <p className="mt-6 text-xs text-slate-500">Послугу пригону надає партнер, а не AUTOforYOU.</p>
        </>
      )}
    </div>
  );
}
