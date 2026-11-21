import { CircleAlert } from 'lucide-react';
import { getErrorMessage } from '@/lib/errors';
import { Button } from '@/components/shadcn/button';
import { ICON_STROKE } from '@/lib/utils';

interface Props {
  error: unknown;
  onRetry?: () => void;
}

/** Помилка завантаження з кнопкою повтору. */
export default function ErrorState({ error, onRetry }: Props) {
  return (
    <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-8 text-center">
      <p className="flex items-center justify-center gap-2 text-sm font-medium text-destructive">
        <CircleAlert className="size-5 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
        {getErrorMessage(error)}
      </p>
      {onRetry && (
        <Button type="button" variant="outline" onClick={onRetry} className="mt-3">
          Спробувати ще раз
        </Button>
      )}
    </div>
  );
}
