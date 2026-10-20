import { requireModule } from '@/lib/site-settings';

// 2.8: модуль заморожено — сторінки лишаються в коді, але віддають 404, поки флаг у .env не увімкнено.
export const dynamic = 'force-dynamic';

export default async function FrozenModuleLayout({ children }: { children: React.ReactNode }) {
  await requireModule('b2b_enabled');
  return <>{children}</>;
}
