import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import Link from 'next/link';
import ErrorState from '@/components/ui/ErrorState';
import LeadForm from '@/components/leads/LeadForm';
import LandingCalc from '@/components/landing/LandingCalc';
import LandingMobileBar, { LANDING_FORM_ID } from '@/components/landing/LandingMobileBar';
import { calculatorHref, getLanding } from '@/lib/landings';
import { CALC_COST_LABEL, HOW_IT_WORKS_LABEL } from '@/lib/labels';
import { buildMetadata } from '@/lib/seo';

// Дані з API: без force-dynamic Next пререндерить сторінку під час build, коли backend недоступний.
// Кеш запиту — LANDING_REVALIDATE_SECONDS (lib/landings.ts).
export const dynamic = 'force-dynamic';

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const result = await getLanding(slug);
  const path = `/prigon/${slug}`;
  // Немає сторінки або збій API: метадані без даних і noindex (сама сторінка — 404 або помилка).
  if (result.status !== 'ok') {
    return buildMetadata({
      title: 'Пригон авто з США',
      description: 'Пригон авто з США під ключ: орієнтовний розрахунок вартості.',
      path,
      noindex: true,
    });
  }
  const p = result.data;
  return buildMetadata({
    title: p.meta_title || `Пригон ${p.make} ${p.model} з США — ціна під ключ`,
    description: p.meta_description || p.intro || `Орієнтовна вартість пригону ${p.make} ${p.model} з США під ключ.`,
    path,
  });
}

function budgetFrom(total: string): string | undefined {
  const n = Math.round(Number(total));
  return Number.isFinite(n) && n > 0 ? String(n) : undefined;
}

export default async function LandingPage({ params }: Params) {
  const { slug } = await params;
  const result = await getLanding(slug);
  if (result.status === 'notfound') notFound();

  if (result.status === 'error') {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10" data-testid="landing-error">
        <h1 className="text-2xl font-bold text-slate-900 mb-6">Пригон авто з США</h1>
        <ErrorState error={null} />
      </div>
    );
  }

  const p = result.data;
  const label = `${p.make} ${p.model}`.trim();
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 pb-28 md:pb-10 space-y-6">
      <header>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900" data-testid="landing-h1">{p.h1}</h1>
        {p.intro && <p className="mt-3 text-slate-700 whitespace-pre-line">{p.intro}</p>}
      </header>

      <LandingCalc calculation={p.calculation} termText={p.typical_term_text} includedText={p.included_text} />

      {p.description && <p className="text-sm text-slate-700 whitespace-pre-line">{p.description}</p>}

      <nav className="flex flex-wrap gap-4 text-sm" aria-label="Корисні посилання">
        <Link href={calculatorHref(p.calculation.inputs)} className="text-blue-700 underline" data-testid="landing-calc-link">
          {CALC_COST_LABEL} під ваші параметри
        </Link>
        <Link href="/how-it-works" className="text-blue-700 underline">{HOW_IT_WORKS_LABEL}</Link>
        <Link href="/prigon" className="text-blue-700 underline">Інші моделі</Link>
      </nav>

      <section id={LANDING_FORM_ID} className="scroll-mt-4">
        <LeadForm source="landing" landingSlug={p.slug} vehicleLabel={label}
          defaultBudgetUsd={budgetFrom(p.calculation.total_usd)} />
      </section>

      <p className="text-xs text-slate-500" data-testid="landing-disclaimer">
        Послугу пригону надає партнер, а не AUTOforYOU.
      </p>

      <LandingMobileBar />
    </div>
  );
}
