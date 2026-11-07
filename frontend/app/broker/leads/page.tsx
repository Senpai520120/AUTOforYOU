import { Suspense } from 'react';
import BrokerLeadList from '@/components/leads/BrokerLeadList';
import Spinner from '@/components/ui/Spinner';

// Дані заявок приватні й залежать від сесії: сторінку не можна пререндерити.
export const dynamic = 'force-dynamic';

export default function BrokerLeadsPage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><Spinner size="lg" /></div>}>
      <BrokerLeadList />
    </Suspense>
  );
}
