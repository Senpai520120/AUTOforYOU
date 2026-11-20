import type { Metadata } from 'next';
import Link from 'next/link';
import EmptyState from '@/components/ui/EmptyState';
import ErrorState from '@/components/ui/ErrorState';
import { getLandingList } from '@/lib/landings';
import { isHowItWorksPublished } from '@/lib/content';
import { CALC_COST_LABEL, HOME_LABEL, HOW_IT_WORKS_LABEL, LANDING_INDEX_LABEL } from '@/lib/labels';
import { buildMetadata } from '@/lib/seo';
import { breadcrumbLd } from '@/lib/jsonld';
import JsonLd from '@/components/seo/JsonLd';
import Breadcrumbs from '@/components/ui/Breadcrumbs';

export const dynamic = 'force-dynamic';

const TITLE = 'Пригон авто з США: моделі та орієнтовна ціна під ключ';

export async function generateMetadata(): Promise<Metadata> {
  const list = await getLandingList();
  return buildMetadata({
    title: TITLE,
    description: 'Моделі авто, які популярно пригонять з США, і орієнтовна вартість пригону під ключ для кожної.',
    path: '/prigon',
    // Порожній список або збій API не індексуються.
    noindex: !list || list.length === 0,
  });
}

export default async function LandingIndexPage() {
  const [list, howItWorksOn] = await Promise.all([getLandingList(), isHowItWorksPublished()]);
  const crumbs = [{ name: HOME_LABEL, path: '/' }, { name: LANDING_INDEX_LABEL, path: '/prigon' }];
  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <JsonLd data={breadcrumbLd(crumbs)} />
      <Breadcrumbs crumbs={crumbs} />
      <h1 className="text-2xl font-bold text-slate-900 mt-4 mb-6">{LANDING_INDEX_LABEL}</h1>

      {list === null && <ErrorState error={null} />}
      {list !== null && list.length === 0 && (
        <div data-testid="landing-index-empty"><EmptyState title="Сторінки моделей скоро з'являться" /></div>
      )}
      {list !== null && list.length > 0 && (
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="landing-index">
          {list.map((l) => (
            <li key={l.slug}>
              <Link href={`/prigon/${l.slug}`} data-testid="landing-index-item"
                className="block bg-white border border-slate-200 rounded-xl p-4 hover:border-blue-400">
                <span className="font-semibold text-slate-900">{l.make} {l.model}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-8 flex flex-wrap gap-4 text-sm">
        {howItWorksOn && <Link href="/how-it-works" className="text-blue-700 underline">{HOW_IT_WORKS_LABEL}</Link>}
        <Link href="/calculator" className="text-blue-700 underline" data-testid="prigon-link-calculator">{CALC_COST_LABEL}</Link>
      </p>
      <p className="mt-4 text-xs text-slate-500">Послугу пригону надає партнер, а не AUTOforYOU.</p>
    </div>
  );
}
