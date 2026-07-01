'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

const STORAGE_KEY = 'cookie_consent';

export default function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setVisible(true);
    }
  }, []);

  const accept = () => {
    localStorage.setItem(STORAGE_KEY, 'all');
    setVisible(false);
  };

  const necessary = () => {
    localStorage.setItem(STORAGE_KEY, 'necessary');
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Налаштування cookie"
      className="fixed bottom-0 inset-x-0 z-50 bg-slate-900 text-white px-4 py-4 shadow-lg"
    >
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <p className="text-sm flex-1">
          Ми використовуємо cookie для коректної роботи сайту.{' '}
          <Link href="/cookies" className="underline hover:text-amber-400 transition-colors">
            Детальніше
          </Link>
        </p>
        <div className="flex gap-3 shrink-0">
          <button
            onClick={necessary}
            className="px-4 py-2 text-sm border border-slate-500 rounded-lg hover:border-slate-300 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            Лише необхідні
          </button>
          <button
            onClick={accept}
            className="px-4 py-2 text-sm bg-amber-500 hover:bg-amber-400 text-black font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400"
          >
            Прийняти всі
          </button>
        </div>
      </div>
    </div>
  );
}
