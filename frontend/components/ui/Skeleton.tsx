import { Skeleton as BaseSkeleton } from '@/components/shadcn/skeleton';

export default function Skeleton({ className = '' }: { className?: string }) {
  return <BaseSkeleton aria-hidden="true" className={`bg-border ${className}`} />;
}

export function ListingCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <Skeleton className="aspect-[4/3] rounded-none" />
      <div className="p-4 space-y-2">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-7 w-1/3 mt-3" />
      </div>
    </div>
  );
}

export function ListingsGridSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
      {Array.from({ length: 8 }).map((_, i) => (
        <ListingCardSkeleton key={i} />
      ))}
    </div>
  );
}
