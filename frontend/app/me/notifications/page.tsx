'use client';
import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getNotifications, markRead, markAllRead } from '@/api/notifications';
import type { AppNotification } from '@/lib/types';

const TYPE_ICON: Record<string, string> = {
  new_message: '💬',
  listing_approved: '✅',
  listing_rejected: '❌',
  listing_expiring: '⏰',
  saved_search_match: '🔔',
};

function timeAgo(iso: string) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'щойно';
  if (diff < 3600) return `${Math.floor(diff / 60)} хв тому`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} год тому`;
  return d.toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' });
}

export default function NotificationsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    getNotifications().then(setItems).catch(() => {}).finally(() => setBusy(false));
  }, [user]);

  const handleClick = async (item: AppNotification) => {
    if (!item.is_read) {
      await markRead(item.id).catch(() => {});
      setItems(prev => prev.map(n => n.id === item.id ? { ...n, is_read: true } : n));
    }
    if (item.link) router.push(item.link);
  };

  const handleMarkAll = async () => {
    await markAllRead().catch(() => {});
    setItems(prev => prev.map(n => ({ ...n, is_read: true })));
  };

  if (loading || !user) return null;

  const unread = items.filter(n => !n.is_read).length;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
        <Link href="/me" className="hover:text-blue-700">Кабінет</Link>
        <span>/</span>
        <span>Сповіщення</span>
      </div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-slate-900">Сповіщення</h1>
        {unread > 0 && (
          <button
            onClick={handleMarkAll}
            className="text-xs text-blue-600 hover:underline"
          >
            Позначити всі прочитаними
          </button>
        )}
      </div>

      {busy ? (
        <div className="text-slate-400 text-sm">Завантаження…</div>
      ) : items.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-slate-400">
          <div className="text-4xl mb-2">🔔</div>
          <p className="text-sm">Немає сповіщень.</p>
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map(item => (
            <li key={item.id}>
              <button
                onClick={() => handleClick(item)}
                className={`w-full text-left rounded-xl border px-4 py-3 transition-colors hover:border-blue-300 ${
                  item.is_read
                    ? 'bg-white border-slate-200 text-slate-600'
                    : 'bg-blue-50 border-blue-200 text-slate-900'
                }`}
              >
                <div className="flex items-start gap-3">
                  <span className="text-xl flex-shrink-0">{TYPE_ICON[item.type] ?? '🔔'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm truncate">{item.title}</span>
                      {!item.is_read && (
                        <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0" />
                      )}
                    </div>
                    {item.text && (
                      <p className="text-xs text-slate-500 mt-0.5 truncate">{item.text}</p>
                    )}
                    <p className="text-xs text-slate-400 mt-0.5">{timeAgo(item.created_at)}</p>
                  </div>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
