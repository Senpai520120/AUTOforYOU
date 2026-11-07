'use client';
import { useEffect } from 'react';
import { reportError } from '@/lib/reportError';

// global-error замінює кореневий layout, тож globals.css тут немає: стилі inline (08-Q17).
const S = {
  body: {
    margin: 0, minHeight: '100vh', display: 'flex', flexDirection: 'column' as const, alignItems: 'center',
    justifyContent: 'center', textAlign: 'center' as const, padding: '0 16px', background: '#f8fafc',
    fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif', color: '#0f172a',
  },
  icon: { fontSize: 60, margin: '0 0 16px' },
  title: { fontSize: 24, fontWeight: 700, margin: '0 0 8px' },
  text: { color: '#64748b', margin: '0 0 32px' },
  button: {
    background: '#1d4ed8', color: '#fff', fontWeight: 600, padding: '12px 24px', border: 0,
    borderRadius: 12, cursor: 'pointer', fontSize: 16,
  },
};

export default function GlobalError({
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
    <html lang="uk">
      <body style={S.body}>
        <p style={S.icon}>⚠</p>
        <h2 style={S.title}>Критична помилка</h2>
        <p style={S.text}>Будь ласка, оновіть сторінку.</p>
        <button onClick={reset} style={S.button}>Оновити</button>
      </body>
    </html>
  );
}
