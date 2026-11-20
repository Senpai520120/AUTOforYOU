'use client';
/**
 * Кнопка «Залишити заявку» поруч з підсумком (10.12): не відправляє, а веде до форми заявки
 * (прокрутка + фокус на перше поле). Якщо форми на сторінці немає (екран успіху) - нічого не робить.
 */
export function scrollToLeadForm(): void {
  const form = document.querySelector<HTMLElement>('[data-testid="lead-form"]');
  if (!form) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  form.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  document.getElementById('lead-name')?.focus({ preventScroll: true });
}

export default function LeadCta({ className = '' }: { className?: string }) {
  return (
    <button type="button" data-testid="lead-cta" onClick={scrollToLeadForm}
      className={`bg-blue-700 hover:bg-blue-800 text-white font-bold py-3 px-6 rounded-xl transition-colors ${className}`}>
      Залишити заявку
    </button>
  );
}
