'use client';
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useRequireAuth } from '@/lib/use-require-auth';
import { localApi } from '@/api/local';
import { ApiError } from '@/api/client';
import { LocalListing } from '@/lib/types';
import LocalListingForm from '@/components/local/LocalListingForm';
import LoadingState from '@/components/ui/LoadingState';
import ErrorState from '@/components/ui/ErrorState';
import EmptyState from '@/components/ui/EmptyState';

export default function EditLocalListingPage() {
  const { user, loading } = useRequireAuth();
  const params = useParams();
  const id = Number(params.id);

  const [listing, setListing] = useState<LocalListing | null>(null);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setFetching(true);
    setError(null);
    localApi.detail(id).then(setListing).catch(setError).finally(() => setFetching(false));
  }, [id]);

  useEffect(() => {
    if (user && id) load();
  }, [user, id, load]);

  if (loading || !user || fetching) return <LoadingState />;

  if (error instanceof ApiError && error.status === 404) {
    return <EmptyState title="Оголошення не знайдено" action={{ label: 'До каталогу', href: '/ua' }} />;
  }
  if (error instanceof ApiError && error.status === 403) {
    return <EmptyState title="Немає доступу" hint="Редагувати можна лише власні оголошення." action={{ label: 'Мої оголошення', href: '/me/local-listings' }} />;
  }
  if (error) return <ErrorState error={error} onRetry={load} />;
  if (!listing) return null;

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Редагувати оголошення</h1>
      <p className="text-sm text-slate-500 mb-8">{listing.make} {listing.model} {listing.year}</p>
      <LocalListingForm initial={listing} listingId={id} />
    </div>
  );
}
