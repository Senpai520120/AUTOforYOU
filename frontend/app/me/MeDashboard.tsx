'use client';
import { useRequireAuth } from '@/lib/use-require-auth';
import Link from 'next/link';
import { useState } from 'react';
import { resendErrorText, resendVerificationEmail } from '@/lib/email-verify';
import { formatDeletionDate } from '@/lib/deletion';
import LoadingState from '@/components/ui/LoadingState';
import { useC2C } from '@/components/c2c/C2CProvider';

const ROLE_LABELS: Record<string, string> = {
  buyer: 'Покупець',
  dealer: 'Перекупник',
  broker: 'Брокер',
  moderator: 'Модератор',
  admin: 'Адмін',
};

function VerifyEmailBanner() {
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [msg, setMsg] = useState('');
  const resend = async () => {
    setState('sending');
    try {
      await resendVerificationEmail();
      setState('sent');
    } catch (err) {
      setMsg(resendErrorText(err));
      setState('error');
    }
  };
  return (
    <div role="status" data-testid="verify-email-banner"
      className="mb-6 bg-amber-50 border border-amber-200 rounded-2xl p-4 text-sm text-amber-900">
      <p className="font-semibold">Підтвердіть email</p>
      <p className="mt-1">Без підтвердження не можна додавати оголошення, писати повідомлення та подавати заявку дилера.</p>
      {state === 'sent' ? (
        <p className="mt-2 font-semibold">Лист надіслано. Перевірте пошту.</p>
      ) : (
        <button type="button" onClick={resend} disabled={state === 'sending'}
          className="mt-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-60 text-black font-semibold px-4 py-1.5 rounded-lg">
          Надіслати ще раз
        </button>
      )}
      {state === 'error' && <p className="mt-2 text-red-700">{msg}</p>}
    </div>
  );
}

function DeletionBanner({ date }: { date: string }) {
  return (
    <div role="status" data-testid="deletion-banner"
      className="mb-6 bg-red-50 border border-red-200 rounded-2xl p-4 text-sm text-red-900">
      <p className="font-semibold">Акаунт буде видалено {formatDeletionDate(date)}</p>
      <p className="mt-1">До цієї дати видалення можна скасувати.</p>
      <Link href="/me/data"
        className="inline-block mt-2 bg-red-600 hover:bg-red-700 text-white font-semibold px-4 py-1.5 rounded-lg">
        Скасувати видалення
      </Link>
    </div>
  );
}

export default function MeDashboard() {
  const { user, loading, logout } = useRequireAuth();
  const c2c = useC2C();

  if (loading || !user) return <LoadingState />;

  // Плитки C2C (переписка, збережені пошуки, мої оголошення, угоди) — лише коли розділ і подача відкриті.
  const C2C_ONLY = ['/me/messages', '/me/saved-searches', '/me/local-listings', '/me/deals'];
  const allItems = [
    { href: '/me/profile', icon: '👤', title: 'Профіль', desc: 'Ім\'я, прізвище, телефон' },
    { href: '/me/notifications', icon: '🔔', title: 'Сповіщення', desc: 'Сповіщення про оголошення та повідомлення' },
    { href: '/me/messages', icon: '💬', title: 'Повідомлення', desc: 'Переписка по оголошеннях' },
    { href: '/me/favorites', icon: '♥', title: 'Обране', desc: 'Збережені оголошення' },
    { href: '/me/saved-searches', icon: '🔍', title: 'Збережені пошуки', desc: 'Сповіщення про нові авто' },
    { href: '/me/local-listings', icon: '📋', title: 'Мої оголошення', desc: 'Каталог Україна — мої авто' },
    { href: '/me/deals', icon: '🤝', title: 'Угоди та відгуки', desc: 'Підтвердження продажу і відгуки' },
    { href: '/me/leads', icon: '📨', title: 'Мої заявки', desc: 'Заявки брокеру та їх статус' },
    { href: '/me/calculations', icon: '🧮', title: 'Мої розрахунки', desc: 'Історія калькуляцій' },
    { href: '/me/trusted-shops', icon: '🔧', title: 'Мої партнери', desc: 'СТО, маляри, запчастини' },
    { href: '/me/security', icon: '🔒', title: 'Безпека', desc: 'Зміна пароля, вихід на всіх пристроях' },
    { href: '/me/telegram', icon: '✈️', title: 'Прив\'язати Telegram', desc: 'Отримуйте сповіщення у Telegram' },
    { href: '/me/data', icon: '🗂️', title: 'Мої дані', desc: 'Завантажити копію даних, видалити акаунт' },
  ];
  const menuItems = allItems.filter(i => c2c.social || !C2C_ONLY.includes(i.href));
  if (user.role === 'broker' || user.is_admin_role) {
    menuItems.unshift({ href: '/broker/leads', icon: '📥', title: 'Заявки', desc: 'Заявки клієнтів і їх статуси' });
  }

  return (
    <div className="max-w-2xl mx-auto">
      {user.deletion_scheduled_for && <DeletionBanner date={user.deletion_scheduled_for} />}
      {!user.is_email_verified && <VerifyEmailBanner />}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-blue-100 rounded-full flex items-center justify-center text-2xl font-bold text-blue-700">
            {user.email[0].toUpperCase()}
          </div>
          <div>
            <h1 className="font-bold text-slate-900 text-lg">{user.first_name || user.email}</h1>
            <p className="text-slate-500 text-sm">{user.email}</p>
            <div className="flex gap-2 mt-1">
              <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded font-semibold">
                {ROLE_LABELS[user.role] ?? 'Покупець'}
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
            <span className="text-3xl" aria-hidden="true">{item.icon}</span>
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
