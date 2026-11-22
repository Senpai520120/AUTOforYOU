import type { Metadata } from 'next';
import Link from 'next/link';
import EmptyState from '@/components/ui/EmptyState';
import ErrorState from '@/components/ui/ErrorState';
import PopularModels from '@/components/landing/PopularModels';
import FaqBlock from '@/components/content/FaqBlock';
import { getHowItWorks } from '@/lib/content';
import { getLandingList } from '@/lib/landings';
import { getSiteConfig } from '@/lib/site-config';
import { partnerPhrase } from '@/lib/site-settings';
import { HOW_IT_WORKS_LABEL, HOW_IT_WORKS_SOON, CALC_COST_LABEL, HOME_LABEL, LANDING_INDEX_LABEL } from '@/lib/labels';
import { buildMetadata } from '@/lib/seo';
import { breadcrumbLd } from '@/lib/jsonld';
import JsonLd from '@/components/seo/JsonLd';

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
  const settings = data?.published ? await getSiteConfig() : null;

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      {data?.published && (
        <JsonLd data={breadcrumbLd([{ name: HOME_LABEL, path: '/' }, { name: HOW_IT_WORKS_LABEL, path: '/how-it-works' }])} />
      )}
      <h1 className="text-2xl font-bold text-foreground mb-6">{HOW_IT_WORKS_LABEL}</h1>

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
              <li key={i} data-testid="import-step" className="bg-card border border-border rounded-xl p-5">
                <h2 className="font-semibold text-foreground">
                  <span className="text-link mr-2">{i + 1}.</span>
                  {step.title}
                </h2>
                {step.duration && <p className="text-xs font-semibold text-muted-foreground mt-1">{step.duration}</p>}
                {step.description && (
                  <p className="text-sm text-muted-foreground mt-2 whitespace-pre-line">{step.description}</p>
                )}
              </li>
            ))}
          </ol>

          <FaqBlock items={data.faq} testId="faq-block" />

          <PopularModels models={models} />

          <div className="mt-10 bg-link/10 border border-link/30 rounded-xl p-5 text-center">
            <Link
              href="/calculator"
              className="inline-block bg-primary hover:bg-primary/90 text-primary-foreground font-bold px-6 py-3 rounded-xl transition-colors"
            >
              {CALC_COST_LABEL}
            </Link>
            <p className="text-sm text-muted-foreground mt-3">
              Заявку на підбір авто можна залишити одразу після розрахунку.
            </p>
          </div>

          {models !== null && models.length > 0 && (
            <p className="mt-6 text-sm">
              <Link href="/prigon" className="text-link underline" data-testid="how-link-prigon">{LANDING_INDEX_LABEL}: моделі та орієнтовна ціна</Link>
            </p>
          )}
          <p className="mt-6 text-xs text-muted-foreground" data-testid="how-partner-phrase">{partnerPhrase(settings?.partner_name)}.</p>
        </>
      )}
    </div>
  );
}
