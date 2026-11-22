'use client';
import { Button } from '@/components/shadcn/button';

export const LANDING_FORM_ID = 'landing-lead';

/**
 * Липка панель з кнопкою «Залишити заявку» (лише мобільні, скрита з md).
 * Прокручує до форми й ставить фокус на перше поле. Панель нижче cookie-плашки (z-40 проти z-50).
 */
export default function LandingMobileBar() {
  const open = () => {
    const form = document.getElementById(LANDING_FORM_ID);
    form?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.setTimeout(() => document.getElementById('lead-name')?.focus({ preventScroll: true }), 400);
  };
  return (
    <div data-testid="landing-mobile-bar"
      className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-card border-t border-border px-4 py-3 shadow-lg">
      <Button type="button" onClick={open} size="lg" className="w-full font-bold">
        Залишити заявку
      </Button>
    </div>
  );
}
