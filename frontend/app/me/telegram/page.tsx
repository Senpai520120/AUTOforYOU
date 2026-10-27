'use client';
import { useRequireAuth } from '@/lib/use-require-auth';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { ApiError, apiFetch } from '@/api/client';
import LoadingState from '@/components/ui/LoadingState';

interface LinkTokenResponse {
  configured: boolean;
  bot_username: string | null;
  token: string | null;
  expires_at: string | null;
  link: string | null;
  note: string | null;
}

// Термін дії посилання: з expires_at відповіді API, а не константа на фронті. «HH:MM» за київським часом.
function validUntil(expiresAt: string | null): string | null {
  if (!expiresAt) return null;
  const d = new Date(expiresAt);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Kyiv' });
}

export default function TelegramPage() {
  const { user, loading, refreshUser } = useRequireAuth();
  const router = useRouter();

  const [generating, setGenerating] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [until, setUntil] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const [unlinking, setUnlinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loading || !user) return <LoadingState />;

  const isLinked = !!user.telegram_id;

  async function handleGenerateLink() {
    setError(null);
    setNotConfigured(false);
    setGenerating(true);
    try {
      const data = await apiFetch<LinkTokenResponse>('/api/v1/telegram/link-token/', { method: 'POST' });
      if (!data.configured || !data.link) {
        setLink(null);
        setNotConfigured(true);
        return;
      }
      setLink(data.link);
      setBotUsername(data.bot_username);
      setUntil(validUntil(data.expires_at));
    } catch (e) {
      const status = e instanceof ApiError ? e.status : undefined;
      setError(
        status === 429
          ? 'Забагато запитів. Спробуйте за годину.'
          : 'Не вдалося отримати посилання. Спробуйте ще раз.',
      );
    } finally {
      setGenerating(false);
    }
  }

  async function handleUnlink() {
    setError(null);
    setUnlinking(true);
    try {
      await apiFetch('/api/v1/telegram/link/', { method: 'DELETE' });
      await refreshUser();
      setLink(null);
    } catch {
      setError('Не вдалося відв\'язати Telegram. Спробуйте ще раз.');
    } finally {
      setUnlinking(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto">
      <button onClick={() => router.back()} className="text-slate-500 hover:text-slate-800 text-sm mb-4 flex items-center gap-1">
        ← Назад
      </button>

      <div className="bg-white border border-slate-200 rounded-2xl p-6">
        <h1 className="text-xl font-bold text-slate-900 mb-1">Telegram</h1>
        <p className="text-sm text-slate-500 mb-6">Отримуйте сповіщення про нові повідомлення, оголошення та угоди прямо в Telegram.</p>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3 mb-4">
            {error}
          </div>
        )}

        {isLinked ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3">
              <span className="text-2xl">✅</span>
              <div>
                <p className="font-semibold text-green-800">Telegram прив'язано</p>
                <p className="text-xs text-green-600">ID: {user.telegram_id}</p>
              </div>
            </div>
            <button
              onClick={handleUnlink}
              disabled={unlinking}
              className="w-full border border-slate-300 hover:border-red-300 hover:text-red-600 text-slate-600 py-2.5 rounded-xl text-sm transition-colors disabled:opacity-50"
            >
              {unlinking ? 'Відв\'язуємо…' : 'Відв\'язати Telegram'}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-3 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
              <span className="text-2xl">🔗</span>
              <p className="text-sm text-slate-600">Telegram ще не прив'язаний до вашого акаунту.</p>
            </div>

            {notConfigured && (
              <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg px-4 py-3">
                Telegram-бот ще не налаштований, спробуйте пізніше.
              </div>
            )}

            {link ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">Натисніть кнопку нижче, щоб відкрити бота і завершити прив'язку:</p>
                <a
                  href={link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block w-full text-center bg-blue-500 hover:bg-blue-600 text-white font-semibold py-3 rounded-xl transition-colors"
                >
                  Відкрити @{botUsername} у Telegram →
                </a>
                <p className="text-xs text-slate-400 text-center">{until ? `Посилання діє до ${until}. ` : ''}Після прив'язки оновіть сторінку.</p>
                <button
                  onClick={handleGenerateLink}
                  className="w-full text-sm text-slate-500 hover:text-slate-700 underline"
                >
                  Отримати нове посилання
                </button>
              </div>
            ) : (
              <button
                onClick={handleGenerateLink}
                disabled={generating}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-xl transition-colors disabled:opacity-50"
              >
                {generating ? 'Генеруємо посилання…' : 'Прив\'язати Telegram'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
