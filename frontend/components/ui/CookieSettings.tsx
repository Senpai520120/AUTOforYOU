'use client';
import { useSyncExternalStore } from 'react';
import { ConsentLevel, clearConsent, getConsent, setConsent, subscribeConsent } from '@/lib/consent';

type Snapshot = ConsentLevel | null | 'unknown';

const getServerSnapshot = (): Snapshot => 'unknown';

const LABELS: Record<ConsentLevel, string> = {
  necessary: 'Лише необхідні',
  all: 'Прийняті всі',
};

export default function CookieSettings() {
  const consent = useSyncExternalStore<Snapshot>(
    subscribeConsent,
    getConsent,
    getServerSnapshot,
  );

  if (consent === 'unknown') {
    return (
      <div className="border border-slate-200 rounded-lg p-4 bg-slate-50 h-28" aria-hidden="true" />
    );
  }

  return (
    <div className="border border-slate-200 rounded-lg p-4 bg-slate-50">
      <p className="text-sm mb-3">
        Ваш поточний вибір:{' '}
        <strong className="text-slate-900">
          {consent === null ? 'ще не зроблено' : LABELS[consent]}
        </strong>
      </p>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => setConsent('necessary')}
          disabled={consent === 'necessary'}
          className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:border-slate-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400"
        >
          Лише необхідні
        </button>
        <button
          type="button"
          onClick={() => setConsent('all')}
          disabled={consent === 'all'}
          className="px-4 py-2 text-sm bg-amber-500 hover:bg-amber-400 text-black font-semibold rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400"
        >
          Прийняти всі
        </button>
        <button
          type="button"
          onClick={clearConsent}
          disabled={consent === null}
          className="px-4 py-2 text-sm text-slate-600 underline hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 rounded"
        >
          Відкликати згоду
        </button>
      </div>
      <p className="text-xs text-slate-500 mt-3">
        Відкликання згоди не видаляє дані, зібрані раніше на законній підставі, і не впливає
        на дані, потрібні для входу в акаунт.
      </p>
    </div>
  );
}
