'use client';
import Modal from '@/components/ui/Modal';

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

/** Підтвердження замість window.confirm. Фокус — на «Скасувати» (Esc/фокус-пастка — в Modal). */
export default function ConfirmDialog({
  open, title, message, confirmLabel = 'Видалити', cancelLabel = 'Скасувати', busy, onConfirm, onCancel,
}: Props) {
  if (!open) return null;
  return (
    <Modal title={title} onClose={onCancel} maxWidth="max-w-sm">
      {message && <p className="text-sm text-slate-600">{message}</p>}
      <div className="flex justify-end gap-3 mt-5">
        <button autoFocus type="button" onClick={onCancel} className="px-4 py-2 text-sm rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50">
          {cancelLabel}
        </button>
        <button type="button" disabled={busy} onClick={onConfirm} className="px-4 py-2 text-sm font-semibold rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50">
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
