'use client';

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
      className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-slate-200 px-4 py-3 shadow-lg">
      <button type="button" onClick={open}
        className="w-full bg-blue-700 hover:bg-blue-800 text-white font-bold py-3 rounded-xl transition-colors">
        Залишити заявку
      </button>
    </div>
  );
}
