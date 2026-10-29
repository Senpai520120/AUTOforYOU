import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import ComingSoon from '@/components/c2c/ComingSoon';
import { getC2CFlags } from '@/lib/c2c';
import { serverGetAuthed } from '@/lib/server-api';
import type { User } from '@/lib/types';

/**
 * Рівень доступу до сторінки:
 * - section: потрібен C2C_ENABLED (каталог, картка);
 * - social: C2C_ENABLED + відкрита подача (переписка, угоди, збережені пошуки);
 * - posting: те саме, але закрите повідомлення «Подача оголошень скоро відкриється» (+ гість → /login).
 */
export type C2CLevel = 'section' | 'social' | 'posting';

async function isOpen(level: C2CLevel) {
  const f = await getC2CFlags();
  if (!f.enabled) return { open: false, variant: 'section' as const, flags: f };
  if (level === 'section') return { open: true, variant: 'section' as const, flags: f };
  return { open: f.postingEnabled, variant: level === 'posting' ? ('posting' as const) : ('section' as const), flags: f };
}

/** noindex для закритого розділу; відкритий — метадані сторінки без змін. */
export async function c2cMetadata(level: C2CLevel): Promise<Metadata> {
  const { open } = await isOpen(level);
  return open ? {} : { robots: { index: false, follow: false } };
}

/** loginNext — якщо задано, гість при закритій подачі іде на вхід (а не бачить заглушку). */
export async function C2CGate({
  level, children, loginNext,
}: { level: C2CLevel; children: React.ReactNode; loginNext?: string }) {
  const { open, variant, flags } = await isOpen(level);
  if (open) return children;
  // Розділ вимкнено: заглушку показує батьківський layout /local, тут не дублюємо редірект.
  if (flags.enabled && loginNext) {
    const user = await serverGetAuthed<User>('/api/v1/auth/profile/');
    if (!user) redirect(`/login?next=${encodeURIComponent(loginNext)}`);
  }
  return <ComingSoon variant={variant} />;
}
