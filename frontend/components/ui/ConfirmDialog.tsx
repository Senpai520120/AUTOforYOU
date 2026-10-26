'use client';
import { useEffect, useId, useRef } from 'react';

interface Props {
  open: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Підтвердження замість window.confirm. Esc закриває, фокус — на «Скасувати». */
export default function ConfirmDialog({
  open, title, message, confirmLabel = 'Видалити', cancelLabel = 'Скасувати', busy, onConfirm, onCancel,
}: Props) {
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6">
        <h2 id={titleId} className="text-base font-bold text-slate-900">{title}</h2>
        {message && <p className="text-sm text-slate-600 mt-2">{message}</p>}
        <div className="flex justify-end gap-3 mt-5">
          <button ref={cancelRef} type="button" onClick={onCancel} className="px-4 py-2 text-sm rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50">
            {cancelLabel}
          </button>
          <button type="button" disabled={busy} onClick={onConfirm} className="px-4 py-2 text-sm font-semibold rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50">
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
