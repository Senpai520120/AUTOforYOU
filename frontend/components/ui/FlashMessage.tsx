'use client';
import { useEffect, useState } from 'react';
import { Info, X } from 'lucide-react';
import { FLASH_KEY } from '@/lib/deletion';
import { ICON_STROKE } from '@/lib/utils';

/** Одноразове повідомлення після переходу (наприклад, «видалення акаунта заплановано»). */
export default function FlashMessage() {
  const [text, setText] = useState('');

  useEffect(() => {
    try {
      const value = window.sessionStorage.getItem(FLASH_KEY);
      if (value) {
        window.sessionStorage.removeItem(FLASH_KEY);
        setText(value);
      }
    } catch {
      // sessionStorage недоступний
    }
  }, []);

  if (!text) return null;
  return (
    <div role="status" data-testid="flash-message"
      className="mb-6 flex items-start gap-3 rounded-xl border border-primary/30 bg-primary/5 p-4 text-sm text-foreground">
      <Info className="mt-0.5 size-5 shrink-0 text-link" strokeWidth={ICON_STROKE} aria-hidden="true" />
      <p className="flex-1">{text}</p>
      <button type="button" onClick={() => setText('')} aria-label="Закрити"
        className="-m-2 inline-flex size-11 items-center justify-center rounded-md text-muted-foreground hover:text-foreground">
        <X className="size-5" strokeWidth={ICON_STROKE} aria-hidden="true" />
      </button>
    </div>
  );
}
