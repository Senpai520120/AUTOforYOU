'use client';
import { useEffect, useState } from 'react';
import { FLASH_KEY } from '@/lib/deletion';

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
      className="mb-6 bg-blue-50 border border-blue-200 rounded-2xl p-4 text-sm text-blue-900 flex items-start gap-3">
      <p className="flex-1">{text}</p>
      <button type="button" onClick={() => setText('')} aria-label="Закрити" className="text-blue-700 hover:text-blue-900">✕</button>
    </div>
  );
}
