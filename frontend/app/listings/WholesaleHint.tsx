'use client';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';

/**
 * Раніше каталог вантажився на клієнті разом з JWT, і дилер бачив тут ще й
 * оптові лоти: ListingListView віддає їх тим, у кого is_verified_dealer.
 *
 * Каталог рендериться на сервері анонімно і кешується (serverGet), тому
 * для всіх однаковий (роздріб), а оптові лоти лишаються там, де для них
 * і є окремий розділ — на B2B-дошці. Авторизований SSR з cookie `access`
 * (serverGetAuthed, задача 1.4) для каталогу не використовується: він
 * вимкнув би кеш сторінки для всіх.
 *
 * Підказка показується тільки тим, хто має до неї доступ.
 */
export default function WholesaleHint() {
  const { user } = useAuth();

  if (!user?.is_verified_dealer) return null;

  return (
    <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-900">
      Ви верифікований дилер. Оптові лоти — на{' '}
      <Link href="/b2b" className="font-semibold underline hover:text-blue-700">
        B2B-дошці
      </Link>
      .
    </div>
  );
}
