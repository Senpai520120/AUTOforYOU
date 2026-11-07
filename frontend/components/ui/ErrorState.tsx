import { getErrorMessage } from '@/lib/errors';

interface Props {
  error: unknown;
  onRetry?: () => void;
}

/** Помилка завантаження з кнопкою повтору. */
export default function ErrorState({ error, onRetry }: Props) {
  return (
    <div role="alert" className="bg-red-50 border border-red-200 rounded-xl p-8 text-center">
      <p className="text-sm text-red-700 font-medium">{getErrorMessage(error)}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 px-4 py-2 text-sm font-semibold rounded-lg bg-white border border-red-300 text-red-700 hover:bg-red-100"
        >
          Спробувати ще раз
        </button>
      )}
    </div>
  );
}
