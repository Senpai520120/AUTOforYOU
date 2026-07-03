'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { dealsApi } from '@/api/deals';
import { Deal } from '@/lib/types';

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  proposed:  { label: 'Очікує підтвердження', cls: 'bg-amber-100 text-amber-800' },
  confirmed: { label: 'Підтверджено',          cls: 'bg-green-100 text-green-800' },
  cancelled: { label: 'Скасовано',             cls: 'bg-slate-100 text-slate-500' },
};

function StarRating({ rating }: { rating: number }) {
  return (
    <span className="text-amber-400">
      {'★'.repeat(rating)}{'☆'.repeat(5 - rating)}
    </span>
  );
}

export default function MyDealsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [fetching, setFetching] = useState(true);
  const [reviewState, setReviewState] = useState<Record<number, { rating: number; text: string }>>({});
  const [submitting, setSubmitting] = useState<number | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    dealsApi.list()
      .then(setDeals)
      .catch(() => {})
      .finally(() => setFetching(false));
  }, [user]);

  const refresh = () => {
    dealsApi.list().then(setDeals).catch(() => {});
  };

  const handleConfirm = async (dealId: number) => {
    setError('');
    try {
      await dealsApi.confirm(dealId);
      refresh();
    } catch {
      setError('Не вдалося підтвердити угоду.');
    }
  };

  const handleCancel = async (dealId: number) => {
    setError('');
    try {
      await dealsApi.cancel(dealId);
      refresh();
    } catch {
      setError('Не вдалося скасувати угоду.');
    }
  };

  const handleReview = async (dealId: number) => {
    const r = reviewState[dealId];
    if (!r?.rating) return;
    setSubmitting(dealId);
    setError('');
    try {
      await dealsApi.review(dealId, { rating: r.rating, text: r.text || '' });
      refresh();
    } catch {
      setError('Не вдалося залишити відгук.');
    } finally {
      setSubmitting(null);
    }
  };

  if (loading || fetching) {
    return <div className="text-center py-16 text-slate-400">Завантаження...</div>;
  }

  const asBuyer = deals.filter(d => d.buyer.id === user?.id);
  const asSeller = deals.filter(d => d.seller.id === user?.id);

  const DealCard = ({ deal, role }: { deal: Deal; role: 'buyer' | 'seller' }) => {
    const badge = STATUS_BADGE[deal.status];
    const isBuyer = role === 'buyer';

    return (
      <div className="border border-slate-200 rounded-xl p-4 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <Link href={`/local/${deal.listing.id}`} className="font-semibold text-blue-700 hover:underline">
              {deal.listing.make} {deal.listing.model} {deal.listing.year}
            </Link>
            <p className="text-xs text-slate-500 mt-0.5">
              {isBuyer ? `Продавець: ${deal.seller.first_name || deal.seller.email}` : `Покупець: ${deal.buyer.first_name || deal.buyer.email}`}
            </p>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
            {badge.label}
          </span>
        </div>

        {deal.status === 'proposed' && isBuyer && (
          <div className="flex gap-2">
            <button
              onClick={() => handleConfirm(deal.id)}
              className="flex-1 bg-green-600 hover:bg-green-500 text-white text-sm font-semibold py-2 rounded-lg transition-colors"
            >
              Підтвердити угоду
            </button>
            <button
              onClick={() => handleCancel(deal.id)}
              className="flex-1 border border-slate-300 text-slate-600 hover:bg-slate-50 text-sm font-semibold py-2 rounded-lg transition-colors"
            >
              Відхилити
            </button>
          </div>
        )}

        {deal.status === 'proposed' && !isBuyer && (
          <button
            onClick={() => handleCancel(deal.id)}
            className="w-full border border-slate-300 text-slate-500 hover:bg-slate-50 text-sm py-1.5 rounded-lg"
          >
            Скасувати пропозицію
          </button>
        )}

        {deal.status === 'confirmed' && isBuyer && !deal.review && (
          <div className="border-t border-slate-100 pt-3 space-y-2">
            <p className="text-sm font-medium text-slate-700">Залишити відгук про продавця:</p>
            <div className="flex gap-1">
              {[1,2,3,4,5].map(star => (
                <button
                  key={star}
                  onClick={() => setReviewState(s => ({ ...s, [deal.id]: { ...s[deal.id], rating: star } }))}
                  className={`text-2xl transition-colors ${(reviewState[deal.id]?.rating || 0) >= star ? 'text-amber-400' : 'text-slate-300 hover:text-amber-300'}`}
                >★</button>
              ))}
            </div>
            <textarea
              placeholder="Напишіть відгук (необов'язково)..."
              rows={2}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none"
              value={reviewState[deal.id]?.text || ''}
              onChange={e => setReviewState(s => ({ ...s, [deal.id]: { ...s[deal.id], text: e.target.value } }))}
            />
            <button
              onClick={() => handleReview(deal.id)}
              disabled={!reviewState[deal.id]?.rating || submitting === deal.id}
              className="w-full bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white text-sm font-semibold py-2 rounded-lg"
            >
              {submitting === deal.id ? 'Надсилаємо...' : 'Надіслати відгук'}
            </button>
          </div>
        )}

        {deal.review && (
          <div className="border-t border-slate-100 pt-3">
            <p className="text-xs text-slate-500 mb-1">Ваш відгук:</p>
            <StarRating rating={deal.review.rating} />
            {deal.review.text && <p className="text-sm text-slate-700 mt-1">{deal.review.text}</p>}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Мої угоди</h1>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-2 text-sm">{error}</div>
      )}

      {deals.length === 0 && (
        <p className="text-slate-500 text-center py-12">Угод поки немає.</p>
      )}

      {asBuyer.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-slate-800 mb-3">Я — покупець</h2>
          <div className="space-y-3">
            {asBuyer.map(d => <DealCard key={d.id} deal={d} role="buyer" />)}
          </div>
        </section>
      )}

      {asSeller.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-slate-800 mb-3">Я — продавець</h2>
          <div className="space-y-3">
            {asSeller.map(d => <DealCard key={d.id} deal={d} role="seller" />)}
          </div>
        </section>
      )}
    </div>
  );
}
