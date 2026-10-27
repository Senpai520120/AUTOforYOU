'use client';
import { useEffect, useState, useRef, useCallback } from 'react';
import { useRequireAuth } from '@/lib/use-require-auth';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getConversations, getConversation, sendMessage } from '@/api/messages';
import LoadingState from '@/components/ui/LoadingState';
import ErrorState from '@/components/ui/ErrorState';
import EmptyState from '@/components/ui/EmptyState';
import { getErrorMessage } from '@/lib/errors';
import EmailNotVerified from '@/components/ui/EmailNotVerified';
import { isEmailNotVerified } from '@/lib/email-verify';
import { useVisibleInterval } from '@/lib/useVisibleInterval';
import { timeAgo } from '@/lib/format';
import type { ConversationSummary, ConversationDetail } from '@/lib/types';

export default function MessagesPage() {
  const { user, loading } = useRequireAuth();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingConvs, setLoadingConvs] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [error, setError] = useState('');
  const [notVerified, setNotVerified] = useState(false);
  const [convError, setConvError] = useState<unknown>(null);
  const [threadError, setThreadError] = useState<unknown>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(async () => {
    setLoadingConvs(true);
    setConvError(null);
    try {
      const data = await getConversations();
      setConversations(data);
    } catch (e) {
      setConvError(e);
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
    setThreadError(null);
    try {
      const data = await getConversation(id);
      setActive(data);
      // mark as read locally
      setConversations(prev =>
        prev.map(c => (c.id === id ? { ...c, unread_count: 0 } : c))
      );
    } catch (e) {
      setThreadError(e);
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

  // poll active thread every 15s (пауза на прихованій вкладці, негайний запит при поверненні)
  const pollThread = useCallback(() => {
    if (!activeId) return;
    getConversation(activeId).then(data => {
      setActive(data);
      setConversations(prev =>
        prev.map(c =>
          c.id === activeId
            ? { ...c, unread_count: 0, last_message_at: data.last_message_at, last_message_text: data.messages.at(-1)?.text.slice(0, 100) ?? c.last_message_text }
            : c
        )
      );
    }).catch(() => {
      // Фоновий опитувальник: помилку не показуємо, наступний цикл повторить запит.
    });
  }, [activeId]);
  useVisibleInterval(pollThread, 15000, !!activeId);

  // scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [active?.messages.length]);

  const handleSend = async () => {
    if (!text.trim() || !activeId || sending) return;
    setSending(true);
    setNotVerified(false);
    try {
      const msg = await sendMessage(activeId, text.trim());
      setText('');
      setActive(prev => prev ? { ...prev, messages: [...prev.messages, msg] } : prev);
      setConversations(prev =>
        prev.map(c =>
          c.id === activeId ? { ...c, last_message_text: msg.text.slice(0, 100), last_message_at: msg.created_at } : c
        )
      );
    } catch (err) {
      if (isEmailNotVerified(err)) setNotVerified(true);
      else setError(getErrorMessage(err));
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  // На < md тред і список не стоять поруч: «назад» скидає активний діалог і ?conv=.
  const backToList = () => {
    setActiveId(null);
    setActive(null);
    router.push('/me/messages');
  };

  if (loading || !user) return <LoadingState />;

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
        <Link href="/me" className="hover:text-blue-700">Кабінет</Link>
        <span>/</span>
        <span>Повідомлення</span>
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-4">Повідомлення</h1>

      {notVerified && <EmailNotVerified className="mb-3" />}
      {error && (
        <div className="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
          {error}
          <button className="ml-2 underline" onClick={() => setError('')}>×</button>
        </div>
      )}

      <div className="flex border border-slate-200 rounded-2xl overflow-hidden bg-white" style={{ minHeight: 480 }}>
        {/* Conversation list */}
        <aside className={`${activeId ? 'hidden md:flex' : 'flex'} w-full md:w-72 border-r border-slate-200 flex-col flex-shrink-0`}>
          <div className="px-4 py-3 border-b border-slate-100 text-sm font-semibold text-slate-700">
            Діалоги
          </div>
          {loadingConvs ? (
            <LoadingState size="md" />
          ) : convError ? (
            <div className="p-3"><ErrorState error={convError} onRetry={loadConversations} /></div>
          ) : conversations.length === 0 ? (
            <div className="flex-1 flex items-center justify-center px-4">
              <EmptyState title="Немає діалогів." hint="Напишіть продавцю з картки оголошення." />
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
                        {conv.other_participant?.display_name || 'Менеджер'}
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
        <div className={`${activeId ? 'flex' : 'hidden md:flex'} flex-1 min-w-0 flex-col`}>
          {!activeId ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
              Оберіть діалог
            </div>
          ) : loadingThread ? (
            <LoadingState size="md" />
          ) : threadError ? (
            <div className="p-4">
              <button type="button" onClick={backToList} className="md:hidden mb-3 text-sm text-blue-700 hover:underline">← Діалоги</button>
              <ErrorState error={threadError} onRetry={() => openConversation(activeId)} />
            </div>
          ) : active ? (
            <>
              {/* Thread header */}
              <div className="px-3 sm:px-5 py-3 border-b border-slate-100 flex items-center gap-3">
                <button
                  type="button"
                  onClick={backToList}
                  className="md:hidden shrink-0 text-sm text-blue-700 hover:underline min-h-8"
                >
                  ← Діалоги
                </button>
                <div className="min-w-0">
                  <div className="font-semibold text-slate-900 text-sm">{active.subject_title}</div>
                  <Link href={active.subject_url} className="text-xs text-blue-600 hover:underline">
                    Переглянути оголошення →
                  </Link>
                </div>
                <button
                  onClick={() => openConversation(activeId)}
                  className="ml-auto text-xs text-slate-400 hover:text-slate-600 transition-colors"
                  title="Оновити"
                  aria-label="Оновити діалог"
                >
                  <span aria-hidden="true">↻</span>
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
                        <div className={`max-w-[85%] sm:max-w-[70%] rounded-2xl px-4 py-2 text-sm ${isMine ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-900'}`}>
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
                  aria-label="Повідомлення" placeholder="Написати повідомлення… (Enter — надіслати)"
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
