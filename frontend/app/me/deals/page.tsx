'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/lib/use-require-auth';
import { dealsApi } from '@/api/deals';
import { Deal } from '@/lib/types';
import LoadingState from '@/components/ui/LoadingState';
import ErrorState from '@/components/ui/ErrorState';
import EmptyState from '@/components/ui/EmptyState';
import { getErrorMessage } from '@/lib/errors';


const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  proposed:  { label: 'Очікує підтвердження', cls: 'bg-warning/15 text-foreground' },
  confirmed: { label: 'Підтверджено',          cls: 'bg-success/10 text-success' },
  cancelled: { label: 'Скасовано',             cls: 'bg-muted text-muted-foreground' },
};

function StarRating({ rating }: { rating: number }) {
  return (
    <span className="text-foreground">
      {'★'.repeat(rating)}{'☆'.repeat(5 - rating)}
    </span>
  );
}

interface DealCardProps {
  deal: Deal;
  role: 'buyer' | 'seller';
  review?: { rating: number; text: string };
  submitting: boolean;
  onConfirm: (id: number) => void;
  onCancel: (id: number) => void;
  onRating: (id: number, rating: number) => void;
  onText: (id: number, text: string) => void;
  onSubmitReview: (id: number) => void;
}

// На рівні модуля: інакше компонент перемонтовується на кожен рендер і поле відгуку втрачає фокус.
function DealCard({ deal, role, review, submitting, onConfirm, onCancel, onRating, onText, onSubmitReview }: DealCardProps) {
  const badge = STATUS_BADGE[deal.status];
  const isBuyer = role === 'buyer';

  return (
    <div className="border border-border rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <Link href={`/local/${deal.listing.id}`} className="font-semibold text-link hover:underline">
            {deal.listing.make} {deal.listing.model} {deal.listing.year}
          </Link>
          <p className="text-xs text-muted-foreground mt-0.5">
            {isBuyer ? `Продавець: ${deal.seller.display_name}` : `Покупець: ${deal.buyer.display_name}`}
          </p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      {deal.status === 'proposed' && isBuyer && (
        <div className="flex gap-2">
          <button
            onClick={() => onConfirm(deal.id)}
            className="flex-1 bg-success hover:bg-success text-success-foreground text-sm font-semibold py-2 rounded-lg transition-colors"
          >
            Підтвердити угоду
          </button>
          <button
            onClick={() => onCancel(deal.id)}
            className="flex-1 border border-input text-muted-foreground hover:bg-muted text-sm font-semibold py-2 rounded-lg transition-colors"
          >
            Відхилити
          </button>
        </div>
      )}

      {deal.status === 'proposed' && !isBuyer && (
        <button
          onClick={() => onCancel(deal.id)}
          className="w-full border border-input text-muted-foreground hover:bg-muted text-sm py-1.5 rounded-lg"
        >
          Скасувати пропозицію
        </button>
      )}

      {deal.status === 'confirmed' && isBuyer && !deal.review && (
        <div className="border-t border-border pt-3 space-y-2">
          <p className="text-sm font-medium text-foreground">Залишити відгук про продавця:</p>
          <div role="radiogroup" aria-label="Оцінка" className="flex gap-1">
            {[1,2,3,4,5].map(star => (
              <button
                key={star}
                type="button"
                role="radio"
                aria-checked={(review?.rating || 0) === star}
                aria-label={`${star} з 5`}
                onClick={() => onRating(deal.id, star)}
                className={`text-2xl transition-colors ${(review?.rating || 0) >= star ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
              ><span aria-hidden="true">{(review?.rating || 0) >= star ? '★' : '☆'}</span></button>
            ))}
          </div>
          <textarea
            aria-label="Відгук про продавця"
            placeholder="Напишіть відгук (необов'язково)..."
            rows={2}
            className="w-full border border-border rounded-lg px-3 py-2 text-sm resize-none"
            value={review?.text || ''}
            onChange={e => onText(deal.id, e.target.value)}
          />
          <button
            onClick={() => onSubmitReview(deal.id)}
            disabled={!review?.rating || submitting}
            className="w-full bg-primary hover:bg-primary disabled:opacity-50 text-primary-foreground text-sm font-semibold py-2 rounded-lg"
          >
            {submitting ? 'Надсилаємо...' : 'Надіслати відгук'}
          </button>
        </div>
      )}

      {deal.review && (
        <div className="border-t border-border pt-3">
          <p className="text-xs text-muted-foreground mb-1">Ваш відгук:</p>
          <StarRating rating={deal.review.rating} />
          {deal.review.text && <p className="text-sm text-foreground mt-1">{deal.review.text}</p>}
        </div>
      )}
    </div>
  );
}

export default function MyDealsPage() {
  const { user, loading } = useRequireAuth();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [fetching, setFetching] = useState(true);
  const [reviewState, setReviewState] = useState<Record<number, { rating: number; text: string }>>({});
  const [submitting, setSubmitting] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState<unknown>(null);

  const load = useCallback(() => {
    setFetching(true);
    setLoadError(null);
    void dealsApi.list()
      .then(setDeals)
      .catch(setLoadError)
      .finally(() => setFetching(false));
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  // Тихе оновлення після дії: збій тут не підміняє список порожнім станом.
  const refresh = () => {
    dealsApi.list().then(setDeals).catch(e => setError(getErrorMessage(e)));
  };

  const handleConfirm = async (dealId: number) => {
    setError('');
    try {
      await dealsApi.confirm(dealId);
      refresh();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  const handleCancel = async (dealId: number) => {
    setError('');
    try {
      await dealsApi.cancel(dealId);
      refresh();
    } catch (e) {
      setError(getErrorMessage(e));
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
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setSubmitting(null);
    }
  };

  const handleRating = (id: number, rating: number) =>
    setReviewState(s => ({ ...s, [id]: { text: s[id]?.text ?? '', rating } }));
  const handleText = (id: number, text: string) =>
    setReviewState(s => ({ ...s, [id]: { rating: s[id]?.rating ?? 0, text } }));

  if (loading || !user || fetching) return <LoadingState />;

  const asBuyer = deals.filter(d => d.buyer.id === user?.id);
  const asSeller = deals.filter(d => d.seller.id === user?.id);

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-foreground mb-6">Мої угоди</h1>

      {error && (
        <div role="alert" className="mb-4 bg-destructive/10 border border-destructive/40 text-destructive rounded-lg px-4 py-2 text-sm">{error}</div>
      )}

      {loadError ? (
        <ErrorState error={loadError} onRetry={load} />
      ) : deals.length === 0 && (
        <EmptyState title="Угод поки немає." hint="Угоди з'являться, коли продавець запропонує вам угоду за оголошенням." />
      )}

      {asBuyer.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-foreground mb-3">Я — покупець</h2>
          <div className="space-y-3">
            {asBuyer.map(d => <DealCard
              key={d.id} deal={d} role="buyer"
              review={reviewState[d.id]}
              submitting={submitting === d.id}
              onConfirm={handleConfirm}
              onCancel={handleCancel}
              onRating={handleRating}
              onText={handleText}
              onSubmitReview={handleReview}
            />)}
          </div>
        </section>
      )}

      {asSeller.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-foreground mb-3">Я — продавець</h2>
          <div className="space-y-3">
            {asSeller.map(d => <DealCard
              key={d.id} deal={d} role="seller"
              review={reviewState[d.id]}
              submitting={submitting === d.id}
              onConfirm={handleConfirm}
              onCancel={handleCancel}
              onRating={handleRating}
              onText={handleText}
              onSubmitReview={handleReview}
            />)}
          </div>
        </section>
      )}
    </div>
  );
}
