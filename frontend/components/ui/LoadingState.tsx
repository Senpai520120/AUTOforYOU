import Spinner from './Spinner';

/** Стан завантаження (role="status" і текст «Завантаження…» — у Spinner). */
export default function LoadingState({ size = 'lg' }: { size?: 'sm' | 'md' | 'lg' }) {
  return (
    <div className="flex justify-center py-16">
      <Spinner size={size} />
    </div>
  );
}
