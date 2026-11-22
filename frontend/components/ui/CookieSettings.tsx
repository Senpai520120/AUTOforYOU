'use client';
import { useSyncExternalStore } from 'react';
import { Button } from '@/components/shadcn/button';
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
      <div className="rounded-xl border bg-card p-4 h-28" aria-hidden="true" />
    );
  }

  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-sm mb-3">
        Ваш поточний вибір:{' '}
        <strong className="text-foreground">
          {consent === null ? 'ще не зроблено' : LABELS[consent]}
        </strong>
      </p>
      <div className="flex flex-wrap gap-3">
        <Button type="button" variant="outline" onClick={() => setConsent('necessary')} disabled={consent === 'necessary'}>
          Лише необхідні
        </Button>
        <Button type="button" onClick={() => setConsent('all')} disabled={consent === 'all'}
          className="bg-accent font-semibold text-accent-foreground hover:bg-accent/90">
          Прийняти всі
        </Button>
        <Button type="button" variant="link" onClick={clearConsent} disabled={consent === null}
          className="text-muted-foreground underline hover:text-foreground">
          Відкликати згоду
        </Button>
      </div>
      <p className="text-xs text-muted-foreground mt-3">
        Відкликання згоди не видаляє дані, зібрані раніше на законній підставі, і не впливає
        на дані, потрібні для входу в акаунт.
      </p>
    </div>
  );
}
