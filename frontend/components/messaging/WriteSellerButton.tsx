'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { startConversation } from '@/api/messages';
import Modal from '@/components/ui/Modal';
import EmailNotVerified from '@/components/ui/EmailNotVerified';
import ScamWarningBanner from '@/components/trust/ScamWarningBanner';
import { isEmailNotVerified } from '@/lib/email-verify';
import { ApiError, getErrorMessage } from '@/lib/errors';
import { CircleAlert, MessageCircle } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Textarea } from '@/components/shadcn/textarea';
import { ICON_STROKE } from '@/lib/utils';

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
      // 4.7: антиспам (400 {text}), ліміт 429, причина сервера; введений текст не губиться.
      const data = e instanceof ApiError ? (e.data as { text?: string[]; detail?: string } | null) : null;
      if (e instanceof ApiError && e.status === 429) setError('Забагато повідомлень, зачекайте');
      else if (data?.text?.length) setError(data.text.join(' '));
      else if (e instanceof ApiError && e.status < 500 && typeof data?.detail === 'string') setError(data.detail);
      else setError(getErrorMessage(e));
      setLoading(false);
    }
  };

  return (
    <>
      <Button type="button" variant="outline" onClick={handleOpen}
        className="w-full border-primary font-semibold text-primary hover:bg-primary/5 hover:text-primary">
        <MessageCircle strokeWidth={ICON_STROKE} aria-hidden="true" />
        {btnLabel}
      </Button>

      {open && (
        <Modal title={btnLabel} onClose={closeModal}>
          <div>
            {notVerified && <EmailNotVerified className="mb-3" />}
            {error && (
              <div role="alert" className="mb-3 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                <CircleAlert className="mt-0.5 size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
                {error}
              </div>
            )}
            {listingType === 'local' && <ScamWarningBanner className="mb-3" />}
            <Textarea
              value={text}
              onChange={e => setText(e.target.value)}
              aria-label="Ваше перше повідомлення"
              placeholder="Ваше перше повідомлення…"
              rows={4}
              autoFocus
              className="resize-none"
            />
            <div className="flex gap-2 mt-4">
              <Button type="button" variant="outline" onClick={closeModal} className="flex-1">
                Скасувати
              </Button>
              <Button type="button" onClick={handleSend} disabled={!text.trim() || loading} className="flex-1 font-semibold">
                {loading ? 'Надсилаю…' : 'Надіслати'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
