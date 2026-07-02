'use client';
import { useEffect, useState, useRef, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getConversations, getConversation, sendMessage } from '@/api/messages';
import type { ConversationSummary, ConversationDetail } from '@/lib/types';

function timeAgo(iso: string) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'щойно';
  if (diff < 3600) return `${Math.floor(diff / 60)} хв тому`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} год тому`;
  return d.toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' });
}

export default function MessagesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingConvs, setLoadingConvs] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  const loadConversations = useCallback(async () => {
    try {
      const data = await getConversations();
      setConversations(data);
    } catch {
      // silently ignore
    } finally {
      setLoadingConvs(false);
    }
  }, []);

  useEffect(() => {
    if (user) loadConversations();
  }, [user, loadConversations]);

  const openConversation = useCallback(async (id: number) => {
    setActiveId(id);
    setLoadingThread(true);
    setActive(null);
    try {
      const data = await getConversation(id);
      setActive(data);
      // mark as read locally
      setConversations(prev =>
        prev.map(c => (c.id === id ? { ...c, unread_count: 0 } : c))
      );
    } catch {
      setError('Не вдалось завантажити діалог.');
    } finally {
      setLoadingThread(false);
    }
  }, []);

  // open conv from URL param ?conv=<id>
  useEffect(() => {
    const convId = searchParams.get('conv');
    if (convId && user) {
      openConversation(Number(convId));
    }
  }, [searchParams, user, openConversation]);

  // poll active thread every 15s
  useEffect(() => {
    if (!activeId) return;
    pollRef.current = setInterval(() => {
      getConversation(activeId).then(data => {
        setActive(data);
        setConversations(prev =>
          prev.map(c =>
            c.id === activeId
              ? { ...c, unread_count: 0, last_message_at: data.last_message_at, last_message_text: data.messages.at(-1)?.text.slice(0, 100) ?? c.last_message_text }
              : c
          )
        );
      }).catch(() => {});
    }, 15000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeId]);

  // scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [active?.messages.length]);

  const handleSend = async () => {
    if (!text.trim() || !activeId || sending) return;
    setSending(true);
    try {
      const msg = await sendMessage(activeId, text.trim());
      setText('');
      setActive(prev => prev ? { ...prev, messages: [...prev.messages, msg] } : prev);
      setConversations(prev =>
        prev.map(c =>
          c.id === activeId ? { ...c, last_message_text: msg.text.slice(0, 100), last_message_at: msg.created_at } : c
        )
      );
    } catch {
      setError('Не вдалось надіслати повідомлення.');
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  if (loading || !user) return null;

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
        <Link href="/me" className="hover:text-blue-700">Кабінет</Link>
        <span>/</span>
        <span>Повідомлення</span>
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-4">Повідомлення</h1>

      {error && (
        <div className="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
          <button className="ml-2 underline" onClick={() => setError('')}>×</button>
        </div>
      )}

      <div className="flex border border-slate-200 rounded-2xl overflow-hidden bg-white" style={{ minHeight: 480 }}>
        {/* Conversation list */}
        <aside className="w-72 border-r border-slate-200 flex flex-col flex-shrink-0">
          <div className="px-4 py-3 border-b border-slate-100 text-sm font-semibold text-slate-700">
            Діалоги
          </div>
          {loadingConvs ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">Завантаження…</div>
          ) : conversations.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm px-4 text-center">
              Немає діалогів.<br />Напишіть продавцю з картки оголошення.
            </div>
          ) : (
            <ul className="flex-1 overflow-y-auto divide-y divide-slate-100">
              {conversations.map(conv => (
                <li key={conv.id}>
                  <button
                    onClick={() => openConversation(conv.id)}
                    className={`w-full text-left px-4 py-3 hover:bg-blue-50 transition-colors ${activeId === conv.id ? 'bg-blue-50 border-l-2 border-blue-600' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-medium text-slate-900 text-sm truncate">
                        {conv.other_participant?.first_name || conv.other_participant?.email?.split('@')[0] || 'Менеджер'}
                      </span>
                      {conv.unread_count > 0 && (
                        <span className="bg-blue-600 text-white text-xs font-bold rounded-full px-1.5 py-0.5 min-w-[20px] text-center">
                          {conv.unread_count}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-blue-700 truncate mt-0.5">{conv.subject_title}</div>
                    <div className="text-xs text-slate-400 truncate mt-0.5">{conv.last_message_text}</div>
                    <div className="text-xs text-slate-300 mt-0.5">{timeAgo(conv.last_message_at)}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        {/* Thread */}
        <div className="flex-1 flex flex-col">
          {!activeId ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
              Оберіть діалог
            </div>
          ) : loadingThread ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
              Завантаження…
            </div>
          ) : active ? (
            <>
              {/* Thread header */}
              <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-3">
                <div>
                  <div className="font-semibold text-slate-900 text-sm">{active.subject_title}</div>
                  <Link href={active.subject_url} className="text-xs text-blue-600 hover:underline">
                    Переглянути оголошення →
                  </Link>
                </div>
                <button
                  onClick={() => openConversation(activeId)}
                  className="ml-auto text-xs text-slate-400 hover:text-slate-600 transition-colors"
                  title="Оновити"
                >
                  ↻
                </button>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
                {active.messages.length === 0 ? (
                  <div className="text-center text-slate-400 text-sm mt-8">Немає повідомлень</div>
                ) : (
                  active.messages.map(msg => {
                    const isMine = msg.sender === user.id;
                    return (
                      <div key={msg.id} className={`flex ${isMine ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[70%] rounded-2xl px-4 py-2 text-sm ${isMine ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-900'}`}>
                          {!isMine && (
                            <div className="text-xs font-semibold mb-1 text-slate-500">{msg.sender_name}</div>
                          )}
                          <p className="whitespace-pre-wrap break-words">{msg.text}</p>
                          <div className={`text-xs mt-1 ${isMine ? 'text-blue-200' : 'text-slate-400'} text-right`}>
                            {timeAgo(msg.created_at)}
                            {isMine && msg.read_at && <span className="ml-1">✓</span>}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={bottomRef} />
              </div>

              {/* Input */}
              <div className="px-5 py-3 border-t border-slate-100 flex gap-2 items-end">
                <textarea
                  value={text}
                  onChange={e => setText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Написати повідомлення… (Enter — надіслати)"
                  rows={2}
                  className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                <button
                  onClick={handleSend}
                  disabled={!text.trim() || sending}
                  className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-semibold px-4 py-2 rounded-xl text-sm transition-colors"
                >
                  {sending ? '…' : 'Надіслати'}
                </button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
