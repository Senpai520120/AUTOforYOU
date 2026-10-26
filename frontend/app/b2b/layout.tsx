import type { Metadata } from 'next';
import { requireModule } from '@/lib/site-settings';

// Модуль заморожено флагом на бекенді (задача 2.8): без флага сторінки дають 404.
// Рендер на кожен запит, інакше під час збірки (backend недоступний) 404 запікся б назавжди.
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'B2B-дошка',
  robots: { index: false, follow: false },
};

export default async function B2BLayout({ children }: { children: React.ReactNode }) {
  await requireModule('b2b');
  return children;
}
