'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useId, useState } from 'react';
import type { C2CFlags } from '@/lib/c2c-flags';

export interface NavLink {
  href: string;
  label: string;
  /** Додатковий клас (акцент для «Каталог Україна»). */
  className?: string;
}

interface NavUser {
  role?: string;
  is_admin_role?: boolean;
}

/**
 * Єдиний список посилань навігації: ним користуються і десктопна nav, і бургер-панель.
 * Умови (прапорець C2C, роль) — в одному місці.
 */
export function getNavLinks(user: NavUser | null, c2c: Pick<C2CFlags, 'enabled'>): NavLink[] {
  const links: NavLink[] = [];
  if (c2c.enabled) links.push({ href: '/ua', label: 'Каталог Україна', className: 'text-amber-300' });
  links.push({ href: '/calculator', label: 'Калькулятор' });
  // role приходить із сервера й клієнтом не змінюється; реальний доступ перевіряє API (403).
  if (user && (user.role === 'broker' || user.is_admin_role)) links.push({ href: '/broker/leads', label: 'Заявки' });
  return links;
}

interface Props {
  links: NavLink[];
  loggedIn: boolean;
  onLogout: () => void;
}

/** Бургер-меню для екранів < md: кнопка + панель під шапкою (шапка має бути `relative`). */
export default function MobileNav({ links, loggedIn, onLogout }: Props) {
  const pathname = usePathname();
  const panelId = useId();
  // Відкрито «на цьому маршруті»: зміна pathname закриває меню без setState в ефекті.
  const [openPath, setOpenPath] = useState<string | null>(null);
  const open = openPath === pathname;
  const close = () => setOpenPath(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenPath(null); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const item = 'block px-4 py-3 text-sm font-medium hover:bg-blue-800 transition-colors';

  return (
    <>
      <button
        type="button"
        aria-label="Меню"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpenPath(open ? null : pathname)}
        className="md:hidden shrink-0 w-9 h-9 -mr-1 flex items-center justify-center rounded hover:bg-blue-800"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          {open
            ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 6l12 12M18 6L6 18" />
            : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />}
        </svg>
      </button>
      <div
        id={panelId}
        hidden={!open}
        className="md:hidden absolute left-0 right-0 top-full z-40 bg-blue-900 border-t border-blue-800 shadow-lg"
      >
        <nav aria-label="Мобільне меню" className="flex flex-col py-1">
          {links.map(l => (
            <Link key={l.href} href={l.href} onClick={close} className={`${item} ${l.className ?? ''}`}>{l.label}</Link>
          ))}
          {loggedIn ? (
            <>
              <Link href="/me" onClick={close} className={item}>Кабінет</Link>
              <button type="button" onClick={() => { close(); onLogout(); }} className={`${item} text-left`}>Вийти</button>
            </>
          ) : (
            <>
              <Link href="/login" onClick={close} className={item}>Увійти</Link>
              <Link href="/register" onClick={close} className={item}>Реєстрація</Link>
            </>
          )}
        </nav>
      </div>
    </>
  );
}
