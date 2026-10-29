'use client';
import { useState, useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { getErrorMessage } from '@/lib/errors';
import { getFavoriteStatus, addFavorite, removeFavorite } from '@/api/favorites';

interface Props {
  listingType: 'local' | 'imported';
  listingId: number;
  size?: 'sm' | 'md';
}

export default function HeartButton({ listingType, listingId, size = 'md' }: Props) {
  const { user } = useAuth();
  const router = useRouter();
  const [isFav, setIsFav] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    getFavoriteStatus(listingType, listingId)
      .then(d => setIsFav(d.is_favorite))
      .catch(() => {
        // Початковий статус не критичний: сердечко лишається незаповненим, дія покаже помилку.
      });
  }, [user, listingType, listingId]);

  const toggle = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!user) { router.push('/login'); return; }
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      if (isFav) {
        await removeFavorite(listingType, listingId);
        setIsFav(false);
      } else {
        await addFavorite(listingType, listingId);
        setIsFav(true);
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const sz = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5';

  return (
    <span className="relative inline-flex">
    <button
      onClick={toggle}
      aria-label={isFav ? 'Прибрати з обраного' : 'Додати в обране'}
      disabled={loading}
      className={`flex items-center justify-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-red-400 ${
        size === 'sm' ? 'p-1' : 'p-2'
      } ${isFav ? 'text-red-500 hover:text-red-400' : 'text-slate-300 hover:text-red-400'}`}
    >
      <svg
        className={sz}
        fill={isFav ? 'currentColor' : 'none'}
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
        />
      </svg>
    </button>
    {error && (
      <span role="alert" className="absolute right-0 top-full mt-1 z-20 whitespace-nowrap rounded bg-red-600 px-2 py-1 text-xs text-white shadow">
        {error}
      </span>
    )}
    </span>
  );
}
