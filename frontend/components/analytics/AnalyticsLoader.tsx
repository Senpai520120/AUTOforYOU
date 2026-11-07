'use client';
import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { apiGet } from '@/api/client';
import { registerLegalVersion, subscribeConsent } from '@/lib/consent';
import { syncProviders, trackPageView, type PublicAnalytics } from '@/lib/analytics';
import type { SiteSettings } from '@/lib/types';

/**
 * Завантажувач аналітики (задача 3.5). Нічого не рендерить.
 * ID беруться з публічних налаштувань (бекенд, .env): зміна ID не потребує пересборки фронту.
 * GA4 стартує лише коли hasAnalyticsConsent() істинний; відкликання згоди прибирає скрипт і cookie.
 * Cloudflare Web Analytics працює без cookie й без згоди.
 *
 * Скрипти вставляються через DOM, а не <Script>: next/script не вміє вивантажувати скрипт
 * після відкликання згоди.
 */
export default function AnalyticsLoader() {
  const pathname = usePathname();
  // Зміна маршруту = новий page_view (автоматичний вимкнено, бо несе адресу з query).
  useEffect(() => { trackPageView(); }, [pathname]);
  useEffect(() => {
    let alive = true;
    let analytics: PublicAnalytics | null = null;
    const unsubscribe = subscribeConsent(() => syncProviders(analytics));
    apiGet<SiteSettings>('/api/v1/site-settings/')
      .then((s) => {
        if (!alive) return;
        // Версія документів потрібна гейту згоди: старе «Прийняти всі» при новій версії не діє.
        // Реєструємо ДО syncProviders, незалежно від того, який запит повернувся раніше (банер або цей).
        registerLegalVersion(
          typeof s?.legal_docs_version === 'string' ? s.legal_docs_version : '',
          s?.legal_docs_reconsent_required === true,
        );
        analytics = s?.analytics ?? null;
        syncProviders(analytics);
      })
      .catch(() => {
        // Налаштування недоступні = аналітики немає.
      });
    return () => {
      alive = false;
      unsubscribe();
      syncProviders(null);
    };
  }, []);
  return null;
}
