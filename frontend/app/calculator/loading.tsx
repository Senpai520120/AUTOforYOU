import Skeleton from '@/components/ui/Skeleton';
import LoadingState from '@/components/ui/LoadingState';

export default function CalculatorLoading() {
  return (
    <div className="max-w-3xl mx-auto">
      <LoadingState size="md" />
      <Skeleton className="h-10 w-1/2 mb-4" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}
