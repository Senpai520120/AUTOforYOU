'use client';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { getUnreadCount } from '@/api/messages';

export default function Header() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!user) { setUnread(0); return; }
    let cancelled = false;
    const load = () => {
      getUnreadCount().then(d => { if (!cancelled) setUnread(d.unread_count); }).catch(() => {});
    };
    load();
    const interval = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [user]);

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  return (
    <header className="bg-blue-900 text-white shadow-md">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-bold text-xl tracking-tight">
          <span className="text-amber-400">AUTO</span>
          <span>forYOU</span>
          <span className="text-xs font-normal text-blue-300 ml-1">Перекупам UA</span>
        </Link>

        <nav className="hidden md:flex items-center gap-6 text-sm font-medium">
          <Link href="/listings" className="hover:text-amber-400 transition-colors">Пригін/аукціон</Link>
          <Link href="/ua" className="hover:text-amber-400 transition-colors text-amber-300">Каталог Україна</Link>
          <Link href="/calculator" className="hover:text-amber-400 transition-colors">Калькулятор</Link>
          {user && (user.is_verified_dealer || user.role === 'admin') ? (
            <Link href="/b2b" className="hover:text-amber-400 transition-colors">B2B</Link>
          ) : user ? (
            <Link href="/dealers/apply" className="text-amber-300 hover:text-amber-400 transition-colors text-xs border border-amber-400/40 px-2 py-1 rounded">
              B2B-доступ
            </Link>
          ) : null}
        </nav>

        <div className="flex items-center gap-3 text-sm">
          {user ? (
            <>
              <Link href="/me/messages" className="relative hover:text-amber-400 transition-colors" aria-label="Повідомлення">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                {unread > 0 && (
                  <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full w-4 h-4 flex items-center justify-center leading-none">
                    {unread > 9 ? '9+' : unread}
                  </span>
                )}
              </Link>
              <Link href="/me" className="hover:text-amber-400 transition-colors">
                {user.email.split('@')[0]}
              </Link>
              <button
                onClick={handleLogout}
                className="bg-blue-700 hover:bg-blue-600 px-3 py-1.5 rounded text-xs transition-colors"
              >
                Выйти
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="hover:text-amber-400 transition-colors">Войти</Link>
              <Link
                href="/register"
                className="bg-amber-500 hover:bg-amber-400 text-black px-3 py-1.5 rounded font-semibold text-xs transition-colors"
              >
                Регистрация
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
