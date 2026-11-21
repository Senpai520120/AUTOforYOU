'use client';
/**
 * Підтвердження телефону через Telegram (задача 4.10): одноразове посилання на бота → «Поділитися контактом».
 *
 * Номер приймається лише власним контактом (перевіряє бот). Після відповіді бота користувач натискає
 * «Перевірити» — профіль перечитується, і батьківський компонент сам показує форму.
 */
import { useState } from 'react';
import { ApiError, apiFetch } from '@/api/client';

interface LinkTokenResponse {
  configured: boolean;
  link: string | null;
}

export default function PhoneVerifyTelegram({ onCheck }: { onCheck: () => Promise<void> }) {
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function getLink() {
    setBusy(true);
    setMessage('');
    try {
      const data = await apiFetch<LinkTokenResponse>('/api/v1/telegram/link-token/', { method: 'POST' });
      if (!data.configured || !data.link) {
        setMessage('Підтвердження через Telegram тимчасово недоступне. Спробуйте пізніше.');
        return;
      }
      setLink(data.link);
    } catch (e) {
      setMessage(e instanceof ApiError && e.status === 429
        ? 'Забагато запитів. Спробуйте за годину.'
        : 'Не вдалося отримати посилання. Спробуйте ще раз.');
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    setBusy(true);
    setMessage('');
    try {
      await onCheck();
      setMessage('Телефон ще не підтверджено. Поділіться контактом у боті й спробуйте ще раз.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="phone-verify-title" className="max-w-xl rounded-xl border border-warning bg-warning/15 p-5 space-y-3">
      <h2 id="phone-verify-title" className="text-lg font-semibold text-foreground">Підтвердіть телефон</h2>
      <p className="text-sm text-foreground">
        Подавати оголошення можуть лише користувачі з підтвердженим телефоном — це захищає покупців від шахраїв.
        Відкрийте нашого бота в Telegram і натисніть «Поділитися контактом».
      </p>
      {!link ? (
        <button type="button" onClick={getLink} disabled={busy}
          className="rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
          Підтвердити через Telegram
        </button>
      ) : (
        <div className="flex flex-wrap gap-2">
          <a href={link} target="_blank" rel="noopener noreferrer"
            className="rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90">
            Відкрити бота в Telegram
          </a>
          <button type="button" onClick={check} disabled={busy}
            className="rounded-lg border border-input bg-card px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-60">
            Я поділився контактом — перевірити
          </button>
        </div>
      )}
      {message && <p role="status" className="text-sm text-foreground">{message}</p>}
    </section>
  );
}
