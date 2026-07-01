'use client';
import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { localApi } from '@/api/local';
import { LocalListing } from '@/lib/types';
import LocalListingForm from '@/components/local/LocalListingForm';

export default function EditLocalListingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const id = Number(params.id);

  const [listing, setListing] = useState<LocalListing | null>(null);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  useEffect(() => {
    if (!id) return;
    localApi.detail(id).then(setListing).catch(() => router.push('/ua')).finally(() => setFetching(false));
  }, [id]);

  if (loading || fetching) return <div className="text-center py-20 text-slate-400">Завантаження...</div>;
  if (!listing) return null;

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Редагувати оголошення</h1>
      <p className="text-sm text-slate-500 mb-8">{listing.make} {listing.model} {listing.year}</p>
      <LocalListingForm initial={listing} listingId={id} />
    </div>
  );
}
