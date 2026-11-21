'use client';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { Button } from '@/components/shadcn/button';
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
      data-on-dark
      className="fixed bottom-0 inset-x-0 z-50 bg-footer text-header-foreground px-4 py-4 shadow-lg"
    >
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <p className="text-xs sm:text-sm flex-1">
          Ми використовуємо файли cookie, потрібні для входу в акаунт і захисту від підроблених
          запитів.
          {hasGa4 && ' Аналітику Google Analytics ми вмикаємо лише з вашої згоди («Прийняти всі»).'}
          {hasCf && ' Статистику відвідувань Cloudflare Web Analytics збираємо без cookie.'}
          {!hasGa4 && !hasCf && ' Інших (аналітичних чи рекламних) cookie ми не використовуємо.'}{' '}
          <Link href="/cookies" className="underline underline-offset-2 hover:text-accent transition-colors">
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
          <Button
            type="button"
            variant="outline"
            onClick={() => choose('necessary')}
            className="border-footer-muted bg-transparent text-header-foreground hover:bg-white/10 hover:text-header-foreground focus-visible:ring-header-foreground"
          >
            Лише необхідні
          </Button>
          <Button
            type="button"
            onClick={() => choose('all')}
            className="bg-accent font-semibold text-accent-foreground hover:bg-accent/90 focus-visible:ring-header-foreground"
          >
            Прийняти всі
          </Button>
          {forceOpen && (
            <Button
              type="button"
              variant="link"
              onClick={() => setForceOpen(false)}
              className="text-footer-foreground underline hover:text-header-foreground focus-visible:ring-header-foreground"
            >
              Закрити
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
