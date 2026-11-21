'use client';
import { useId, useState } from 'react';
import Modal from '@/components/ui/Modal';
import { useAuth } from '@/lib/auth-context';
import { reportsApi } from '@/api/reports';
import { ReportReason } from '@/lib/types';
import { ApiError, firstDataMessage, getErrorMessage } from '@/lib/errors';
import { CircleAlert, Flag } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Label } from '@/components/shadcn/label';
import { Textarea } from '@/components/shadcn/textarea';
import { ICON_STROKE } from '@/lib/utils';
import { FIELD_CLASS } from '@/components/local/field-classes';

interface Props {
  listingId?: number;
  reportedUserId?: number;
  className?: string;
}

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'spam', label: 'Спам або реклама' },
  { value: 'wrong_info', label: 'Недостовірна інформація' },
  { value: 'inappropriate', label: 'Неприпустимий контент' },
  { value: 'fraud', label: 'Шахрайство' },
  { value: 'duplicate', label: 'Дублікат оголошення' },
  { value: 'other', label: 'Інше' },
];

export default function ReportButton({ listingId, reportedUserId, className = '' }: Props) {
  const { user } = useAuth();
  const reasonId = useId();
  const commentId = useId();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ReportReason>('spam');
  const [comment, setComment] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  if (!user) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await reportsApi.create({
        ...(listingId ? { listing: listingId } : {}),
        ...(reportedUserId ? { reported_user: reportedUserId } : {}),
        reason,
        comment,
      });
      setDone(true);
    } catch (err: unknown) {
      // 10-Q6: причина відмови сервера з err.data (detail, non_field_errors, перше поле).
      const fromServer = err instanceof ApiError && err.status < 500 ? firstDataMessage(err.data) : null;
      setError(fromServer ?? (err instanceof ApiError ? getErrorMessage(err) : 'Не вдалося подати скаргу.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(true)}
        className={`text-muted-foreground hover:text-destructive ${className}`}>
        <Flag strokeWidth={ICON_STROKE} aria-hidden="true" />
        Поскаржитися
      </Button>

      {open && (
        <Modal title="Поскаржитися" onClose={() => setOpen(false)}>
          <div>

            {done ? (
              <div className="text-center py-4">
                <p className="text-success font-medium mb-1">Скаргу подано.</p>
                <p className="text-sm text-muted-foreground">Ми розглянемо її найближчим часом.</p>
                <Button type="button" variant="secondary" onClick={() => { setOpen(false); setDone(false); }} className="mt-4">
                  Закрити
                </Button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <Label htmlFor={reasonId} className="mb-1.5">Причина</Label>
                  <select
                    id={reasonId}
                    value={reason}
                    onChange={e => setReason(e.target.value as ReportReason)}
                    className={FIELD_CLASS}
                  >
                    {REASONS.map(r => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor={commentId} className="mb-1.5">Коментар (необов'язково)</Label>
                  <Textarea
                    id={commentId}
                    value={comment}
                    onChange={e => setComment(e.target.value)}
                    rows={3}
                    className="resize-none"
                    placeholder="Опишіть проблему..."
                  />
                </div>
                {error && (
                  <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
                    <CircleAlert className="mt-0.5 size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
                    {error}
                  </p>
                )}
                <div className="flex gap-2 justify-end">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                    Скасувати
                  </Button>
                  <Button type="submit" variant="destructive" disabled={loading}>
                    {loading ? 'Надсилаємо...' : 'Подати скаргу'}
                  </Button>
                </div>
              </form>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
