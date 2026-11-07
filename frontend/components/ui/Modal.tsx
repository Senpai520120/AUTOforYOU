'use client';
import { useEffect, useId, useRef } from 'react';

interface Props {
  /** Заголовок: на нього вказує aria-labelledby. */
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  /** Tailwind-клас максимальної ширини вікна. */
  maxWidth?: string;
  /** Кнопка «×» у шапці (aria-label «Закрити»). */
  showClose?: boolean;
  /** Закривати по кліку на підкладку. */
  closeOnBackdrop?: boolean;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Модальне вікно: role="dialog", Esc і клік по підкладці закривають,
 * фокус заходить усередину та повертається на кнопку-джерело, Tab не виходить за межі.
 * Рендерити лише коли вікно відкрите: `{open && <Modal …/>}`.
 */
export default function Modal({
  title, onClose, children, maxWidth = 'max-w-md', showClose = false, closeOnBackdrop = true,
}: Props) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const source = document.activeElement as HTMLElement | null;
    // autoFocus дочірнього елемента вже міг спрацювати — тоді не чіпаємо.
    if (!dialog.contains(document.activeElement)) {
      const first = dialog.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? dialog).focus();
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== 'Tab') return;
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        e.preventDefault();
        dialog.focus();
        return;
      }
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === firstEl || active === dialog || !dialog.contains(active))) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && (active === lastEl || !dialog.contains(active))) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (source && source.isConnected) source.focus();
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onMouseDown={e => { if (closeOnBackdrop && e.target === e.currentTarget) onClose(); }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`bg-white rounded-2xl shadow-xl w-full ${maxWidth} max-h-[90vh] overflow-y-auto p-6 outline-none`}
      >
        {showClose ? (
          <div className="flex items-start justify-between gap-3 mb-3">
            <h2 id={titleId} className="text-lg font-bold text-slate-900">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Закрити"
              className="text-slate-500 hover:text-slate-700 text-xl leading-none px-1"
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>
        ) : (
          <h2 id={titleId} className="text-lg font-bold text-slate-900 mb-3">{title}</h2>
        )}
        {children}
      </div>
    </div>
  );
}
