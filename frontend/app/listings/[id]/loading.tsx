import Skeleton from '@/components/ui/Skeleton';

export default function ListingDetailLoading() {
  return (
    <div>
      <Skeleton className="h-4 w-20 mb-4" />
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <Skeleton className="h-80 rounded-xl" />
        <div className="space-y-4">
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-10 w-1/3" />
          <div className="grid grid-cols-2 gap-3 mt-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
          <Skeleton className="h-11 w-48 mt-4" />
        </div>
      </div>
    </div>
  );
}
