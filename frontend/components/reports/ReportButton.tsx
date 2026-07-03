'use client';
import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { reportsApi } from '@/api/reports';
import { ReportReason } from '@/lib/types';

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
      const msg = (err as { detail?: string })?.detail || 'Не вдалося подати скаргу.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={`text-xs text-slate-400 hover:text-red-500 transition-colors ${className}`}
      >
        Поскаржитися
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-bold mb-4">Поскаржитися</h3>

            {done ? (
              <div className="text-center py-4">
                <p className="text-green-700 font-medium mb-1">Скаргу подано.</p>
                <p className="text-sm text-slate-500">Ми розглянемо її найближчим часом.</p>
                <button
                  onClick={() => { setOpen(false); setDone(false); }}
                  className="mt-4 px-4 py-2 bg-slate-100 rounded-lg text-sm hover:bg-slate-200"
                >
                  Закрити
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Причина</label>
                  <select
                    value={reason}
                    onChange={e => setReason(e.target.value as ReportReason)}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  >
                    {REASONS.map(r => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Коментар (необов'язково)</label>
                  <textarea
                    value={comment}
                    onChange={e => setComment(e.target.value)}
                    rows={3}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none"
                    placeholder="Опишіть проблему..."
                  />
                </div>
                {error && <p className="text-sm text-red-600">{error}</p>}
                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg"
                  >
                    Скасувати
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg disabled:opacity-60"
                  >
                    {loading ? 'Надсилаємо...' : 'Подати скаргу'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
