'use client';
import Modal from '@/components/ui/Modal';
import { Button } from '@/components/shadcn/button';

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
      {message && <p className="text-sm text-muted-foreground">{message}</p>}
      <div className="flex justify-end gap-3 mt-5">
        <Button autoFocus type="button" variant="outline" onClick={onCancel}>
          {cancelLabel}
        </Button>
        <Button type="button" variant="destructive" disabled={busy} onClick={onConfirm} className="font-semibold">
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
