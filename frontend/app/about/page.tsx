import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import Breadcrumbs from '@/components/ui/Breadcrumbs';
import JsonLd from '@/components/seo/JsonLd';
import { getAbout } from '@/lib/about';
import { ABOUT_LABEL, HOME_LABEL } from '@/lib/labels';
import { buildMetadata } from '@/lib/seo';
import { breadcrumbLd } from '@/lib/jsonld';

// Дані з API: без force-dynamic Next пререндерить сторінку під час build, коли backend недоступний.
export const dynamic = 'force-dynamic';

export async function generateMetadata(): Promise<Metadata> {
  const text = await getAbout();
  return buildMetadata({
    title: ABOUT_LABEL,
    description: text ? text.slice(0, 160) : ABOUT_LABEL,
    path: '/about',
    noindex: !text,
  });
}

export default async function AboutPage() {
  const text = await getAbout();
  // Порожній текст або збій API: сторінки немає.
  if (!text) notFound();
  const crumbs = [{ name: HOME_LABEL, path: '/' }, { name: ABOUT_LABEL, path: '/about' }];
  const paragraphs = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <JsonLd data={breadcrumbLd(crumbs)} />
      <Breadcrumbs crumbs={crumbs} />
      <h1 className="text-2xl font-bold text-foreground mt-4 mb-6">{ABOUT_LABEL}</h1>
      <div data-testid="about-text" className="space-y-4 text-foreground">
        {paragraphs.map((p, i) => <p key={i} className="whitespace-pre-line">{p}</p>)}
      </div>
    </div>
  );
}
