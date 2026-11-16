import Link from 'next/link';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import LocalListingCard from '@/components/local/LocalListingCard';
import EmptyState from '@/components/ui/EmptyState';
import { sellerPath } from '@/api/sellers';
import { INTERNAL_API_URL } from '@/lib/config.server';
import { publicMedia } from '@/lib/server-api';
import { isC2CEnabled } from '@/lib/c2c';
import { buildMetadata } from '@/lib/seo';
import { SELLER_NOT_FOUND, VERIFIED_DEALER_LABEL, memberSinceLabel } from '@/lib/labels';
import type { SellerProfile } from '@/lib/types';

// Дані продавця змінюються з кожним оголошенням; під час збірки бекенд недоступний.
export const dynamic = 'force-dynamic';

type Params = Promise<{ id: string }>;
type Search = Promise<{ page?: string | string[] }>;

type Loaded = { kind: 'ok'; seller: SellerProfile } | { kind: 'not-found' } | { kind: 'error' };

async function loadSeller(id: string, page: number): Promise<Loaded> {
  if (!/^\d{1,10}$/.test(id)) return { kind: 'not-found' };
  try {
    const res = await fetch(`${INTERNAL_API_URL}${sellerPath(id, page)}`, { cache: 'no-store' });
    if (res.status === 404) return { kind: 'not-found' };
    if (!res.ok) return { kind: 'error' };
    return { kind: 'ok', seller: publicMedia((await res.json()) as SellerProfile) };
  } catch {
    return { kind: 'error' };
  }
}

function pageNumber(raw: string | string[] | undefined): number {
  const n = Number(Array.isArray(raw) ? raw[0] : raw);
  return Number.isInteger(n) && n > 1 ? n : 1;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id } = await params;
  // Поки власник не вирішив інакше — сторінки продавців не індексуються (8.6).
  const data = (await isC2CEnabled()) ? await loadSeller(id, 1) : { kind: 'not-found' as const };
  const title = data.kind === 'ok' ? `Продавець ${data.seller.display_name}` : SELLER_NOT_FOUND;
  // У canonical — лише id з відповіді сервера, не сирий сегмент URL.
  const path = data.kind === 'ok' ? `/sellers/${data.seller.id}` : '/local';
  return buildMetadata({ title, description: `${title}: оголошення та відгуки на AUTOforYOU`, path, noindex: true });
}

function Stars({ value }: { value: number }) {
  const r = Math.max(0, Math.min(5, Math.round(value)));
  return <span className="text-amber-400" aria-label={`Оцінка ${value.toFixed(1)} з 5`}>{'★'.repeat(r)}{'☆'.repeat(5 - r)}</span>;
}

export default async function SellerPage({ params, searchParams }: { params: Params; searchParams: Search }) {
  if (!(await isC2CEnabled())) notFound();
  const { id } = await params;
  let page = pageNumber((await searchParams).page);
  let data = await loadSeller(id, page);
  // ?page= більше за кількість сторінок: DRF віддає 404 — показуємо першу сторінку, а не «не знайдено».
  if (data.kind === 'not-found' && page > 1) {
    page = 1;
    data = await loadSeller(id, 1);
  }

  if (data.kind === 'not-found') {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10">
        <EmptyState title={SELLER_NOT_FOUND} hint="Можливо, акаунт видалено або в продавця немає активних оголошень." action={{ label: 'До оголошень', href: '/local' }} />
      </div>
    );
  }
  if (data.kind === 'error') {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10">
        <div role="alert" className="bg-red-50 border border-red-200 rounded-xl p-8 text-center text-sm text-red-700">
          Не вдалося завантажити сторінку продавця. Спробуйте оновити сторінку пізніше.
        </div>
      </div>
    );
  }

  const s = data.seller;
  const since = memberSinceLabel(s.member_since);
  const { results, next, previous } = s.listings;
  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <section data-testid="seller-profile" className="bg-white border border-slate-100 rounded-xl p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-bold text-slate-900">{s.display_name}</h1>
          {s.is_verified_dealer && (
            <span data-testid="verified-dealer" className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-semibold">
              ✓ {VERIFIED_DEALER_LABEL}
            </span>
          )}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600">
          {since && <span>{since}</span>}
          <span>Активних оголошень: {s.active_listings_count}</span>
          <span>Підтверджених угод: {s.deal_count}</span>
          {s.avg_rating !== null && (
            <span data-testid="seller-rating" className="flex items-center gap-1">
              <Stars value={s.avg_rating} /> {s.avg_rating.toFixed(1)}
            </span>
          )}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="font-semibold text-slate-900 mb-3">Оголошення продавця</h2>
        {results.length === 0 ? (
          <EmptyState title="Активних оголошень зараз немає" />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {results.map((l) => <LocalListingCard key={l.id} listing={l} />)}
          </div>
        )}
        {(previous || next) && (
          <nav aria-label="Сторінки" className="mt-6 flex justify-center gap-3 text-sm">
            {previous && <Link className="text-blue-700 hover:underline" href={`/sellers/${s.id}?page=${page - 1}`}>← Попередня</Link>}
            <span className="text-slate-500">Сторінка {page}</span>
            {next && <Link className="text-blue-700 hover:underline" href={`/sellers/${s.id}?page=${page + 1}`}>Наступна →</Link>}
          </nav>
        )}
      </section>

      {s.reviews.length > 0 && (
        <section className="mt-8">
          <h2 className="font-semibold text-slate-900 mb-3">Відгуки</h2>
          <ul className="space-y-3">
            {s.reviews.map((r, i) => (
              <li key={i} className="bg-white border border-slate-100 rounded-xl p-4 text-sm">
                <div className="flex items-center gap-2">
                  <Stars value={r.rating} />
                  <span className="text-slate-700 font-medium">{r.author_name}</span>
                  <span className="text-slate-400 text-xs">{new Date(r.created_at).toLocaleDateString('uk-UA')}</span>
                </div>
                {r.text && <p className="mt-1 text-slate-700 whitespace-pre-line">{r.text}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
