'use client';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { useCallback, useEffect, useState } from 'react';
import { getUnreadCount as getMsgUnread } from '@/api/messages';
import { getUnreadCount as getNotifUnread } from '@/api/notifications';
import { useVisibleInterval } from '@/lib/useVisibleInterval';
import { useC2C } from '@/components/c2c/C2CProvider';
import MobileNav, { getNavLinks } from '@/components/layout/MobileNav';

export default function Header() {
  const { user, logout } = useAuth();
  const c2c = useC2C();
  // Переписка закрита (C2C вимкнено або «засів») — іконки й опитування messages/unread-count немає.
  const chatOpen = c2c.social;
  const [msgUnread, setMsgUnread] = useState(0);
  const [notifUnread, setNotifUnread] = useState(0);

  const loadCounts = useCallback(() => {
    if (chatOpen) getMsgUnread().then(d => setMsgUnread(d.unread_count)).catch(() => {});
    getNotifUnread().then(d => setNotifUnread(d.unread_count)).catch(() => {});
  }, [chatOpen]);

  useEffect(() => {
    if (!user) { setMsgUnread(0); setNotifUnread(0); return; }
    if (!chatOpen) setMsgUnread(0);
    loadCounts();
  }, [user, chatOpen, loadCounts]);

  // Опит кожні 30 с; на прихованій вкладці пауза, при поверненні — одразу.
  useVisibleInterval(loadCounts, 30000, !!user);

  const navLinks = getNavLinks(user, c2c);
  const handleLogout = () => { void logout(); };

  return (
    <header className="relative bg-blue-900 text-white shadow-md">
      <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <Link href="/" className="flex items-center gap-2 font-bold text-xl tracking-tight shrink-0">
          <span className="text-amber-400">AUTO</span>
          <span>forYOU</span>
        </Link>

        <nav className="hidden md:flex items-center gap-6 text-sm font-medium">
          {navLinks.map(l => (
            <Link key={l.href} href={l.href} className={`hover:text-amber-400 transition-colors ${l.className ?? ''}`}>{l.label}</Link>
          ))}
        </nav>

        <div className="flex items-center gap-3 text-sm min-w-0">
          {user ? (
            <>
              {/* Notifications bell */}
              <Link href="/me/notifications" className="relative hover:text-amber-400 transition-colors" aria-label="Сповіщення">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
                {notifUnread > 0 && (
                  <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full w-4 h-4 flex items-center justify-center leading-none">
                    {notifUnread > 9 ? '9+' : notifUnread}
                  </span>
                )}
              </Link>
              {/* Chat icon */}
              {chatOpen && <Link href="/me/messages" className="relative hover:text-amber-400 transition-colors" aria-label="Повідомлення">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                {msgUnread > 0 && (
                  <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full w-4 h-4 flex items-center justify-center leading-none">
                    {msgUnread > 9 ? '9+' : msgUnread}
                  </span>
                )}
              </Link>}
              <Link href="/me" className="hover:text-amber-400 transition-colors hidden sm:inline truncate min-w-0 max-w-[16rem]">
                {user.email.split('@')[0]}
              </Link>
              <button
                onClick={handleLogout}
                className="hidden sm:inline-block bg-blue-700 hover:bg-blue-600 px-3 py-1.5 rounded text-xs transition-colors shrink-0"
              >
                Вийти
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="hover:text-amber-400 transition-colors">Увійти</Link>
              <Link
                href="/register"
                className="bg-amber-500 hover:bg-amber-400 text-black px-3 py-1.5 rounded font-semibold text-xs transition-colors"
              >
                Реєстрація
              </Link>
            </>
          )}
          <MobileNav links={navLinks} loggedIn={!!user} onLogout={handleLogout} />
        </div>
      </div>
    </header>
  );
}
