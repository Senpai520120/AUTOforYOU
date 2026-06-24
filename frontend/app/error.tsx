'use client';
import { useEffect } from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <p className="text-6xl mb-4">⚠</p>
      <h2 className="text-2xl font-bold text-slate-900 mb-2">Щось пішло не так</h2>
      <p className="text-slate-500 mb-8 max-w-sm">
        Сталася помилка при завантаженні сторінки. Спробуйте ще раз.
      </p>
      <div className="flex gap-3">
        <button
          onClick={reset}
          className="bg-blue-700 hover:bg-blue-800 text-white font-semibold px-6 py-3 rounded-xl transition-colors"
        >
          Повторити
        </button>
        <a
          href="/listings"
          className="border border-slate-300 hover:border-blue-300 text-slate-700 font-semibold px-6 py-3 rounded-xl transition-colors"
        >
          Каталог
        </a>
      </div>
    </div>
  );
}
