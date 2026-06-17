'use client';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import Link from 'next/link';

export default function MePage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  if (loading || !user) return null;

  const menuItems = [
    { href: '/me/calculations', icon: '🧮', title: 'Мої розрахунки', desc: 'Історія калькуляцій' },
    { href: '/me/trusted-shops', icon: '🔧', title: 'Мої партнери', desc: 'СТО, маляри, запчастини' },
    { href: '/me/shipments', icon: '📦', title: 'Мої контейнери', desc: 'Відстежувані шипменти' },
  ];

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-blue-100 rounded-full flex items-center justify-center text-2xl font-bold text-blue-700">
            {user.email[0].toUpperCase()}
          </div>
          <div>
            <p className="font-bold text-slate-900 text-lg">{user.first_name || user.email}</p>
            <p className="text-slate-500 text-sm">{user.email}</p>
            <div className="flex gap-2 mt-1">
              <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded font-semibold">
                {user.role === 'dealer' ? 'Перекупник' : user.role === 'admin' ? 'Адмін' : 'Покупець'}
              </span>
              {user.is_verified_dealer && (
                <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded font-semibold">✓ Верифіковано</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4">
        {menuItems.map(item => (
          <Link key={item.href} href={item.href}
            className="bg-white border border-slate-200 rounded-xl p-5 flex items-center gap-4 hover:shadow-md hover:border-blue-300 transition-all group">
            <span className="text-3xl">{item.icon}</span>
            <div>
              <p className="font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">{item.title}</p>
              <p className="text-sm text-slate-500">{item.desc}</p>
            </div>
            <span className="ml-auto text-slate-400 group-hover:text-blue-600">→</span>
          </Link>
        ))}
      </div>

      <button onClick={logout} className="mt-6 w-full border border-slate-300 hover:border-red-300 hover:text-red-600 text-slate-600 py-2 rounded-xl text-sm transition-colors">
        Вийти
      </button>
    </div>
  );
}
