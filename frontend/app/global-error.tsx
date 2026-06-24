'use client';
import { useEffect } from 'react';

export default function GlobalError({
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
    <html lang="uk">
      <body className="flex flex-col items-center justify-center min-h-screen bg-slate-50 text-center px-4">
        <p className="text-6xl mb-4">⚠</p>
        <h2 className="text-2xl font-bold text-slate-900 mb-2">Критична помилка</h2>
        <p className="text-slate-500 mb-8">Будь ласка, оновіть сторінку.</p>
        <button
          onClick={reset}
          className="bg-blue-700 text-white font-semibold px-6 py-3 rounded-xl"
        >
          Оновити
        </button>
      </body>
    </html>
  );
}
