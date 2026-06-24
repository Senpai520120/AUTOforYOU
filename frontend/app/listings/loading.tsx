import { ListingsGridSkeleton } from '@/components/ui/Skeleton';

export default function ListingsLoading() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Каталог автомобілів</h1>
      <div className="mt-6">
        <ListingsGridSkeleton />
      </div>
    </div>
  );
}
