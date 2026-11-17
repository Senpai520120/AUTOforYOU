'use client';
import { useState } from 'react';
import { resendErrorText, resendVerificationEmail } from '@/lib/email-verify';

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
    <div role="alert" className={`text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 ${className}`}>
      <p>Підтвердіть email, щоб виконати цю дію. Ми надіслали лист із посиланням на вашу пошту.</p>
      {state === 'sent' ? (
        <p className="mt-1 font-semibold">Лист надіслано. Перевірте пошту.</p>
      ) : (
        <button type="button" onClick={resend} disabled={state === 'sending'}
          className="mt-1 underline font-semibold disabled:opacity-60">
          Надіслати лист ще раз
        </button>
      )}
      {state === 'error' && <p className="mt-1 text-red-700">{msg}</p>}
    </div>
  );
}
