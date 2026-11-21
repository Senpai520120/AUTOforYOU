'use client';
import { useState } from 'react';
import { resendErrorText, resendVerificationEmail } from '@/lib/email-verify';
import { TriangleAlert } from 'lucide-react';
import { ICON_STROKE } from '@/lib/utils';

/** Повідомлення «Підтвердіть email» з посиланням на повторну відправку листа. */
export default function EmailNotVerified({ className = '' }: { className?: string }) {
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [msg, setMsg] = useState('');

  const resend = async () => {
    setState('sending');
    try {
      await resendVerificationEmail();
      setState('sent');
    } catch (err) {
      setMsg(resendErrorText(err));
      setState('error');
    }
  };

  return (
    <div role="alert" className={`flex items-start gap-2 text-sm text-foreground bg-warning/15 border border-warning rounded-lg px-4 py-3 ${className}`}>
      <TriangleAlert className="mt-0.5 size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
      <div>
      <p>Підтвердіть email, щоб виконати цю дію. Ми надіслали лист із посиланням на вашу пошту.</p>
      {state === 'sent' ? (
        <p className="mt-1 font-semibold">Лист надіслано. Перевірте пошту.</p>
      ) : (
        <button type="button" onClick={resend} disabled={state === 'sending'}
          className="mt-1 inline-flex min-h-11 items-center underline font-semibold disabled:opacity-60">
          Надіслати лист ще раз
        </button>
      )}
      {state === 'error' && <p className="mt-1 text-destructive">{msg}</p>}
      </div>
    </div>
  );
}
