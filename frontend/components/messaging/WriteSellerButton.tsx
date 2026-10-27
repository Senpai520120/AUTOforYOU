'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { startConversation } from '@/api/messages';
import Modal from '@/components/ui/Modal';
import EmailNotVerified from '@/components/ui/EmailNotVerified';
import { isEmailNotVerified } from '@/lib/email-verify';

interface Props {
  listingType: 'local' | 'imported';
  listingId: number;
  label?: string;
}

export default function WriteSellerButton({ listingType, listingId, label }: Props) {
  const { user } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notVerified, setNotVerified] = useState(false);

  const btnLabel = label ?? (listingType === 'imported' ? 'Написати менеджеру' : 'Написати продавцю');

  const handleOpen = () => {
    if (!user) { router.push('/login'); return; }
    setOpen(true);
  };

  const closeModal = () => { setOpen(false); setError(''); setText(''); };

  const handleSend = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError('');
    setNotVerified(false);
    try {
      const res = await startConversation(listingType, listingId, text.trim());
      router.push(`/me/messages?conv=${res.conversation_id}`);
    } catch (e: unknown) {
      if (isEmailNotVerified(e)) {
        setNotVerified(true);
        setLoading(false);
        return;
      }
      const err = e as { data?: { detail?: string } };
      setError(err?.data?.detail ?? 'Помилка. Спробуйте ще раз.');
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={handleOpen}
        className="w-full bg-green-600 hover:bg-green-500 text-white font-semibold py-2.5 rounded-lg transition-colors text-sm"
      >
        {btnLabel}
      </button>

      {open && (
        <Modal title={btnLabel} onClose={closeModal}>
          <div>
            {notVerified && <EmailNotVerified className="mb-3" />}
            {error && (
              <div role="alert" className="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{error}</div>
            )}
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              aria-label="Ваше перше повідомлення"
              placeholder="Ваше перше повідомлення…"
              rows={4}
              autoFocus
              className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <div className="flex gap-2 mt-4">
              <button
                onClick={closeModal}
                className="flex-1 border border-slate-300 text-slate-600 hover:border-slate-400 py-2 rounded-xl text-sm transition-colors"
              >
                Скасувати
              </button>
              <button
                onClick={handleSend}
                disabled={!text.trim() || loading}
                className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-semibold py-2 rounded-xl text-sm transition-colors"
              >
                {loading ? 'Надсилаю…' : 'Надіслати'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
