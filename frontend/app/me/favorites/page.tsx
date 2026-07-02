'use client';
import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { getFavorites, removeFavorite } from '@/api/favorites';
import type { FavoriteItem } from '@/lib/types';

const PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='150' viewBox='0 0 200 150'%3E%3Crect width='200' height='150' fill='%23e2e8f0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='12' fill='%2394a3b8'%3EФото відсутнє%3C/text%3E%3C/svg%3E";

export default function FavoritesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    getFavorites().then(setItems).catch(() => {}).finally(() => setBusy(false));
  }, [user]);

  const remove = async (item: FavoriteItem) => {
    try {
      await removeFavorite(item.listing_type, item.listing_id);
      setItems(prev => prev.filter(f => f.id !== item.id));
    } catch {
      // ignore
    }
  };

  if (loading || !user) return null;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
        <Link href="/me" className="hover:text-blue-700">Кабінет</Link>
        <span>/</span>
        <span>Обране</span>
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-4">Обране</h1>

      {busy ? (
        <div className="text-slate-400 text-sm">Завантаження…</div>
      ) : items.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-slate-400">
          <div className="text-4xl mb-2">♡</div>
          <p className="text-sm">Тут будуть збережені оголошення.</p>
          <Link href="/ua" className="mt-3 inline-block text-blue-600 hover:underline text-sm">
            Переглянути Каталог Україна →
          </Link>
        </div>
      ) : (
        <ul className="grid gap-4">
          {items.map(item => (
            <li key={item.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden flex gap-4 hover:shadow-md transition-shadow">
              <Link href={item.url} className="flex-shrink-0 relative w-32 h-24 bg-slate-100">
                <Image
                  src={item.image_url || PLACEHOLDER}
                  alt={item.title}
                  fill
                  className="object-cover"
                  sizes="128px"
                  onError={(e) => { (e.currentTarget as HTMLImageElement).src = PLACEHOLDER; }}
                />
              </Link>
              <div className="flex-1 py-3 pr-4 flex flex-col justify-between">
                <div>
                  <Link href={item.url} className="font-semibold text-slate-900 hover:text-blue-700 transition-colors text-sm">
                    {item.title}
                  </Link>
                  {item.price && (
                    <div className="text-sm text-slate-600 mt-0.5">
                      {Number(item.price).toLocaleString('uk-UA')} {item.currency}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-2">
                  <Link
                    href={item.url}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Переглянути →
                  </Link>
                  <button
                    onClick={() => remove(item)}
                    className="text-xs text-slate-400 hover:text-red-500 transition-colors"
                  >
                    Прибрати
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
