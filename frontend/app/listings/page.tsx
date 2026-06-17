import { Suspense } from 'react';
import ListingFilters from '@/components/listings/ListingFilters';
import ListingsGrid from './ListingsGrid';
import Spinner from '@/components/ui/Spinner';

export const metadata = { title: 'Каталог авто — AUTOforYOU' };

export default function ListingsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Каталог автомобілів</h1>
      <Suspense>
        <ListingFilters />
      </Suspense>
      <div className="mt-6">
        <Suspense fallback={<div className="flex justify-center py-20"><Spinner size="lg" /></div>}>
          <ListingsGrid />
        </Suspense>
      </div>
    </div>
  );
}
