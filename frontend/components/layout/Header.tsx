'use client';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { useCallback, useEffect, useState } from 'react';
import { getUnreadCount as getMsgUnread } from '@/api/messages';
import { getUnreadCount as getNotifUnread } from '@/api/notifications';
import { useVisibleInterval } from '@/lib/useVisibleInterval';
import { useC2C } from '@/components/c2c/C2CProvider';
import { PRIMARY_CTA_LABEL } from '@/lib/labels';
import { Bell, MessageSquare } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { ICON_STROKE } from '@/lib/utils';
import MobileNav, { getNavLinks } from '@/components/layout/MobileNav';

export default function Header({ hasLandings = false }: { hasLandings?: boolean }) {
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

  const navLinks = getNavLinks(user, c2c, hasLandings);
  const handleLogout = () => { void logout(); };

  return (
    <header data-on-dark className="relative bg-header text-header-foreground shadow-md">
      <div className="max-w-7xl mx-auto px-4 py-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <Link href="/" className="flex items-center gap-2 min-h-11 font-bold text-xl tracking-tight shrink-0">
          <span className="text-accent">AUTO</span>
          <span>forYOU</span>
        </Link>

        <nav className="hidden md:flex items-center gap-6 text-sm font-medium">
          {navLinks.map(l => (
            <Link key={l.href} href={l.href} className={`inline-flex items-center min-h-11 hover:text-accent transition-colors ${l.className ?? ''}`}>{l.label}</Link>
          ))}
        </nav>

        <div className="flex items-center gap-3 text-sm min-w-0">
          <Button
            asChild
            size="sm"
            className="min-h-11 bg-accent text-accent-foreground hover:bg-accent/90 focus-visible:ring-header-foreground text-xs font-semibold shrink-0"
          >
            <Link href="/calculator" data-testid="header-primary-cta">{PRIMARY_CTA_LABEL}</Link>
          </Button>
          {user ? (
            <>
              {/* Notifications bell */}
              <Link href="/me/notifications" className="relative inline-flex items-center justify-center min-w-11 min-h-11 hover:text-accent transition-colors" aria-label="Сповіщення">
                <Bell className="size-5" strokeWidth={ICON_STROKE} aria-hidden="true" />
                {notifUnread > 0 && (
                  <span className="absolute -top-1 -right-1 bg-destructive text-destructive-foreground text-xs font-bold rounded-full min-w-4 min-h-4 px-0.5 flex items-center justify-center leading-none">
                    {notifUnread > 9 ? '9+' : notifUnread}
                  </span>
                )}
              </Link>
              {/* Chat icon */}
              {chatOpen && <Link href="/me/messages" className="relative inline-flex items-center justify-center min-w-11 min-h-11 hover:text-accent transition-colors" aria-label="Повідомлення">
                <MessageSquare className="size-5" strokeWidth={ICON_STROKE} aria-hidden="true" />
                {msgUnread > 0 && (
                  <span className="absolute -top-1 -right-1 bg-destructive text-destructive-foreground text-xs font-bold rounded-full min-w-4 min-h-4 px-0.5 flex items-center justify-center leading-none">
                    {msgUnread > 9 ? '9+' : msgUnread}
                  </span>
                )}
              </Link>}
              <Link href="/me" className="hover:text-accent transition-colors hidden sm:inline-flex items-center min-h-11 truncate min-w-0 max-w-[16rem]">
                {user.email.split('@')[0]}
              </Link>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                className="hidden sm:inline-flex min-h-11 bg-header-foreground/15 text-header-foreground hover:bg-header-foreground/25 hover:text-header-foreground focus-visible:ring-header-foreground focus-visible:border-header-foreground text-xs shrink-0"
              >
                Вийти
              </Button>
            </>
          ) : (
            <>
              <Link href="/login" className="inline-flex items-center min-h-11 px-1 hover:text-accent transition-colors">Увійти</Link>
              <Link href="/register" className="inline-flex items-center min-h-11 px-1 hover:text-accent transition-colors">Реєстрація</Link>
            </>
          )}
          <MobileNav links={navLinks} loggedIn={!!user} onLogout={handleLogout} />
        </div>
      </div>
    </header>
  );
}
