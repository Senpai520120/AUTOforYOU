'use client';
import { useEffect } from 'react';
import Link from 'next/link';
import { reportError } from '@/lib/reportError';

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportError(error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4" data-testid="error-page">
      <p className="text-6xl mb-4">⚠</p>
      <h2 className="text-2xl font-bold text-foreground mb-2">Щось пішло не так</h2>
      <p className="text-muted-foreground mb-8 max-w-sm">
        Сталася помилка при завантаженні сторінки. Спробуйте ще раз.
      </p>
      <div className="flex gap-3">
        <button
          onClick={reset}
          className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold px-6 py-3 rounded-xl transition-colors"
        >
          Повторити
        </button>
        <Link
          href="/"
          className="border border-input hover:border-ring text-foreground font-semibold px-6 py-3 rounded-xl transition-colors"
        >
          На головну
        </Link>
        <Link
          href="/calculator"
          className="border border-input hover:border-ring text-foreground font-semibold px-6 py-3 rounded-xl transition-colors"
        >
          Калькулятор
        </Link>
      </div>
    </div>
  );
}
