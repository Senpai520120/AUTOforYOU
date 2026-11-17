'use client';
import { useRequireAuth } from '@/lib/use-require-auth';
import Spinner from '@/components/ui/Spinner';

// Гість -> /login (useRequireAuth). Право на заявки визначає сервер: сторінки показують
// «Доступ обмежено» на 403 від API, а не за полем role на клієнті.
export default function BrokerLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useRequireAuth();
  if (loading || !user) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>;
  return <div className="max-w-6xl mx-auto">{children}</div>;
}
