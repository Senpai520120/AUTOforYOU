'use client';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';

export default function Header() {
  const { user, logout } = useAuth();
  const router = useRouter();

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
          <Link href="/listings" className="hover:text-amber-400 transition-colors">Каталог</Link>
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
