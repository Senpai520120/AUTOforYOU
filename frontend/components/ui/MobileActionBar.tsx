'use client';
/**
 * Нижня панель дій на мобільній картці (задача 6.6).
 *
 * - Лише `< md`; закріплена внизу з урахуванням `env(safe-area-inset-bottom)`.
 * - Поки видно банер cookie, стоїть над ним (`--cookie-banner-h` пише CookieBanner).
 * - Ховається, поки фокус у полі вводу (екранна клавіатура); нижче за модалки (z-40 < z-50).
 * - Сама додає сторінці нижній відступ (spacer), щоб останній блок не ховався під нею.
 * - Клік рахується у внутрішніх лічильниках без ПДн (`mobile_bar_click`, 8.7) і, лише зі згодою,
 *   в аналітиці (3.5) — тільки по кнопках самої панелі (`countBarClick` в їхньому onClick);
 *   помилка відправки на дію не впливає. Діалоги в панелі не рендеряться: «Написати» відкриває
 *   той самий діалог на сторінці (інакше модалка опинилась би всередині fixed-панелі).
 */
import { useEffect, useState, type ReactNode } from 'react';
import { trackEvent } from '@/lib/analytics';
import { sendMetric } from '@/lib/metrics';

export interface MobileAction {
  key: string;
  /** Готовий елемент (посилання, кнопка або компонент з власним діалогом). */
  node: ReactNode;
}

const BAR_HEIGHT = '4.25rem';
const TEXT_INPUT = 'input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]):not([type=hidden]), textarea, select, [contenteditable="true"]';

export const mobileBarButtonClass =
  'flex w-full min-h-11 items-center justify-center rounded-lg px-3 py-2.5 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-ring';

function useTyping(): boolean {
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    const update = () => {
      const el = document.activeElement;
      setTyping(!!el && el instanceof Element && el.matches(TEXT_INPUT));
    };
    const onOut = () => window.setTimeout(update, 0); // activeElement оновлюється після focusout
    document.addEventListener('focusin', update);
    document.addEventListener('focusout', onOut);
    return () => {
      document.removeEventListener('focusin', update);
      document.removeEventListener('focusout', onOut);
    };
  }, []);
  return typing;
}

export function countBarClick(): void {
  sendMetric('mobile_bar_click');
  trackEvent('mobile_bar_click', { source: 'listing' });
}

export default function MobileActionBar({ actions, label = 'Дії з оголошенням' }: {
  actions: MobileAction[];
  label?: string;
}) {
  const typing = useTyping();
  if (!actions.length) return null;
  return (
    <>
      <div aria-hidden="true" className="md:hidden"
        style={{ height: `calc(${BAR_HEIGHT} + env(safe-area-inset-bottom) + var(--cookie-banner-h, 0px))` }} />
      <nav
        aria-label={label}
        data-testid="mobile-action-bar"
        hidden={typing}
        className="md:hidden fixed inset-x-0 z-40 border-t border-border bg-card/95 backdrop-blur px-3 pt-2 shadow-[0_-2px_8px_rgba(0,0,0,0.06)]"
        style={{
          bottom: 'var(--cookie-banner-h, 0px)',
          paddingBottom: 'calc(0.5rem + env(safe-area-inset-bottom))',
        }}
      >
        <div className="mx-auto flex max-w-5xl gap-2">
          {actions.map((a) => (
            // Кнопки з чужих компонентів (WriteSellerButton) теж не нижчі за 44 px.
            <div key={a.key} className="min-w-0 flex-1 [&>a]:min-h-11 [&>button]:min-h-11">{a.node}</div>
          ))}
        </div>
      </nav>
    </>
  );
}
