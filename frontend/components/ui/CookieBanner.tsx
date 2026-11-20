'use client';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { fetchSiteSettings } from '@/lib/site-settings-client';
import {
  getRawConsent,
  parseConsent,
  registerLegalVersion,
  setConsent,
  shouldAskAgain,
  subscribeConsent,
  subscribeConsentOpen,
} from '@/lib/consent';

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
  const [hasGa4, setHasGa4] = useState(false);
  const [hasCf, setHasCf] = useState(false);

  // Публічні налаштування: версія документів і прапор повторної згоди. Недоступне API
  // (або помилка) -> без версії, банер поводиться як раніше.
  useEffect(() => {
    let alive = true;
    fetchSiteSettings()
      .then((s) => {
        if (!alive) return;
        const version = typeof s?.legal_docs_version === 'string' ? s.legal_docs_version : '';
        const reconsent = s?.legal_docs_reconsent_required === true;
        registerLegalVersion(version, reconsent);
        setLegal({ version, reconsent });
        setHasGa4(!!s?.analytics?.ga4_id);
        setHasCf(!!s?.analytics?.cloudflare_token);
      })
      .catch(() => { if (alive) registerLegalVersion(''); });
    return () => { alive = false; };
  }, []);

  useEffect(() => subscribeConsentOpen(() => setForceOpen(true)), []);

  const stored = raw === 'unknown' ? null : parseConsent(raw);
  const ask = stored === null || shouldAskAgain(stored.version, legal.version, legal.reconsent);
  const visible = raw !== 'unknown' && (ask || forceOpen);

  // 6.6: висота банера в --cookie-banner-h, щоб нижня мобільна панель стояла над ним; 0 — коли банера немає.
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const docEl = document.documentElement;
    const el = rootRef.current;
    if (!visible || !el) {
      docEl.style.setProperty('--cookie-banner-h', '0px');
      return;
    }
    const publish = () => docEl.style.setProperty('--cookie-banner-h', `${el.offsetHeight}px`);
    publish();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(publish) : null;
    observer?.observe(el);
    return () => {
      observer?.disconnect();
      docEl.style.setProperty('--cookie-banner-h', '0px');
    };
  }, [visible]);

  if (!visible) return null;

  const choose = (level: 'necessary' | 'all') => {
    setConsent(level, legal.version || null);
    setForceOpen(false);
  };

  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-label="Налаштування файлів cookie"
      className="fixed bottom-0 inset-x-0 z-50 bg-slate-900 text-white px-4 py-4 shadow-lg"
    >
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <p className="text-xs sm:text-sm flex-1">
          Ми використовуємо файли cookie, потрібні для входу в акаунт і захисту від підроблених
          запитів.
          {hasGa4 && ' Аналітику Google Analytics ми вмикаємо лише з вашої згоди («Прийняти всі»).'}
          {hasCf && ' Статистику відвідувань Cloudflare Web Analytics збираємо без cookie.'}
          {!hasGa4 && !hasCf && ' Інших (аналітичних чи рекламних) cookie ми не використовуємо.'}{' '}
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
