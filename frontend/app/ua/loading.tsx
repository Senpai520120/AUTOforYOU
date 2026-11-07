import { ListingsGridSkeleton } from '@/components/ui/Skeleton';
import LoadingState from '@/components/ui/LoadingState';

export default function UaLoading() {
  return (
    <div>
      <LoadingState size="md" />
      <ListingsGridSkeleton />
    </div>
  );
}
