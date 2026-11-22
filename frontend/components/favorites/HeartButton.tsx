'use client';
import { useState, useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { getErrorMessage } from '@/lib/errors';
import { getFavoriteStatus, addFavorite, removeFavorite } from '@/api/favorites';
import { Heart } from 'lucide-react';
import { ICON_STROKE } from '@/lib/utils';

interface Props {
  listingType: 'local' | 'imported';
  listingId: number;
  size?: 'sm' | 'md';
}

export default function HeartButton({ listingType, listingId, size = 'md' }: Props) {
  const { user } = useAuth();
  const router = useRouter();
  // Статус привʼязаний до (тип, id): при зміні оголошення або виході з акаунта
  // старе значення не показується (isFav = false), без setState в ефекті.
  const key = `${listingType}:${listingId}`;
  const [fav, setFav] = useState<{ key: string; value: boolean } | null>(null);
  const isFav = Boolean(user) && fav?.key === key && fav.value;
  const setIsFav = (value: boolean) => setFav({ key, value });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    getFavoriteStatus(listingType, listingId)
      .then(d => { if (!cancelled) setFav({ key, value: d.is_favorite }); })
      .catch(() => {
        // Початковий статус не критичний: сердечко лишається незаповненим, дія покаже помилку.
      });
    return () => { cancelled = true; };
  }, [user, listingType, listingId, key]);

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

  const sz = size === 'sm' ? 'size-4' : 'size-5';

  return (
    <span className="relative inline-flex">
    <button
      onClick={toggle}
      aria-label={isFav ? 'Прибрати з обраного' : 'Додати в обране'}
      disabled={loading}
      className={`flex items-center justify-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-ring ${
        size === 'sm' ? 'p-1' : 'p-2'
      } ${isFav ? 'text-destructive' : 'text-muted-foreground hover:text-destructive'}`}
    >
      <Heart className={sz} fill={isFav ? 'currentColor' : 'none'} strokeWidth={ICON_STROKE} aria-hidden="true" />
    </button>
    {error && (
      <span role="alert" className="absolute right-0 top-full mt-1 z-20 whitespace-nowrap rounded bg-destructive px-2 py-1 text-xs text-destructive-foreground shadow">
        {error}
      </span>
    )}
    </span>
  );
}
