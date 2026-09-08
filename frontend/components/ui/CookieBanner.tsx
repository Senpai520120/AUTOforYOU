'use client';
import { useSyncExternalStore } from 'react';
import Link from 'next/link';
import { ConsentLevel, getConsent, setConsent, subscribeConsent } from '@/lib/consent';

// 'unknown' — на сервері та під час гідратації вибір ще не прочитано.
// Банер не рендериться, доки стан невідомий: інакше він блимав би у тих,
// хто вже зробив вибір.
type Snapshot = ConsentLevel | null | 'unknown';

const getServerSnapshot = (): Snapshot => 'unknown';

export default function CookieBanner() {
  const consent = useSyncExternalStore<Snapshot>(
    subscribeConsent,
    getConsent,
    getServerSnapshot,
  );

  if (consent !== null) return null;

  return (
    <div
      role="dialog"
      aria-label="Налаштування файлів cookie"
      className="fixed bottom-0 inset-x-0 z-50 bg-slate-900 text-white px-4 py-4 shadow-lg"
    >
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <p className="text-sm flex-1">
          Ми зберігаємо у вашому браузері дані, потрібні для входу в акаунт. Аналітичні та
          рекламні сервіси зараз не використовуються — вони не запрацюють без вашої згоди.{' '}
          <Link href="/cookies" className="underline hover:text-amber-400 transition-colors">
            Що саме зберігається
          </Link>
        </p>
        <div className="flex gap-3 shrink-0">
          <button
            type="button"
            onClick={() => setConsent('necessary')}
            className="px-4 py-2 text-sm border border-slate-500 rounded-lg hover:border-slate-300 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            Лише необхідні
          </button>
          <button
            type="button"
            onClick={() => setConsent('all')}
            className="px-4 py-2 text-sm bg-amber-500 hover:bg-amber-400 text-black font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400"
          >
            Прийняти всі
          </button>
        </div>
      </div>
    </div>
  );
}
