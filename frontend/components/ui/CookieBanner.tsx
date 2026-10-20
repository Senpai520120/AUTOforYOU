'use client';
import { useEffect, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { apiGet } from '@/api/client';
import {
  getRawConsent,
  parseConsent,
  registerLegalVersion,
  setConsent,
  shouldAskAgain,
  subscribeConsent,
  subscribeConsentOpen,
} from '@/lib/consent';
import type { SiteSettings } from '@/lib/types';

// 'unknown' — на сервері та під час гідратації вибір ще не прочитано.
// Банер не рендериться, доки стан невідомий: інакше він блимав би у тих,
// хто вже зробив вибір. Знімок — сирий рядок (примітив), розбір — нижче.
type Snapshot = string | null | 'unknown';

const getServerSnapshot = (): Snapshot => 'unknown';

const LEVEL_LABELS = { necessary: 'Лише необхідні', all: 'Прийняті всі' } as const;

export default function CookieBanner() {
  const raw = useSyncExternalStore<Snapshot>(subscribeConsent, getRawConsent, getServerSnapshot);
  const [legal, setLegal] = useState<{ version: string; reconsent: boolean }>({ version: '', reconsent: false });
  const [forceOpen, setForceOpen] = useState(false);

  // Публічні налаштування: версія документів і прапор повторної згоди. Недоступне API
  // (або помилка) -> без версії, банер поводиться як раніше.
  useEffect(() => {
    let alive = true;
    apiGet<SiteSettings>('/api/v1/site-settings/')
      .then((s) => {
        if (!alive) return;
        const version = typeof s?.legal_docs_version === 'string' ? s.legal_docs_version : '';
        const reconsent = s?.legal_docs_reconsent_required === true;
        registerLegalVersion(version, reconsent);
        setLegal({ version, reconsent });
      })
      .catch(() => { if (alive) registerLegalVersion(''); });
    return () => { alive = false; };
  }, []);

  useEffect(() => subscribeConsentOpen(() => setForceOpen(true)), []);

  if (raw === 'unknown') return null;
  const stored = parseConsent(raw);
  const ask = stored === null || shouldAskAgain(stored.version, legal.version, legal.reconsent);
  if (!ask && !forceOpen) return null;

  const choose = (level: 'necessary' | 'all') => {
    setConsent(level, legal.version || null);
    setForceOpen(false);
  };

  return (
    <div
      role="dialog"
      aria-label="Налаштування файлів cookie"
      className="fixed bottom-0 inset-x-0 z-50 bg-slate-900 text-white px-4 py-4 shadow-lg"
    >
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <p className="text-sm flex-1">
          Ми використовуємо файли cookie, потрібні для входу в акаунт і захисту від підроблених
          запитів. Аналітичні та
          рекламні сервіси зараз не використовуються — вони не запрацюють без вашої згоди.{' '}
          <Link href="/cookies" className="underline hover:text-amber-400 transition-colors">
            Що саме зберігається
          </Link>
          {stored && (
            <>
              {' '}
              <span data-testid="cookie-current-choice">
                Ваш поточний вибір: {LEVEL_LABELS[stored.level]}.
              </span>
            </>
          )}
        </p>
        <div className="flex flex-wrap gap-3 shrink-0">
          <button
            type="button"
            onClick={() => choose('necessary')}
            className="px-4 py-2 text-sm border border-slate-500 rounded-lg hover:border-slate-300 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            Лише необхідні
          </button>
          <button
            type="button"
            onClick={() => choose('all')}
            className="px-4 py-2 text-sm bg-amber-500 hover:bg-amber-400 text-black font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400"
          >
            Прийняти всі
          </button>
          {forceOpen && (
            <button
              type="button"
              onClick={() => setForceOpen(false)}
              className="px-4 py-2 text-sm text-slate-300 underline hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 rounded"
            >
              Закрити
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
