/**
 * Мінімальний звіт про помилку фронтенду в моніторинг (задача 7.6, 08-Q17).
 *
 * Йде на бекенд (`/api/v1/monitoring/client-errors/`), той пересилає в Sentry/GlitchTip:
 * DSN у клієнтський JS не потрапляє. Стек і дані користувача не надсилаються, шлях — без query.
 */
const ENDPOINT = '/api/v1/monitoring/client-errors/';

export type ErrorReport = {
  message: string;
  digest?: string;
  path?: string;
  component?: 'frontend' | 'frontend-ssr';
};

export function buildReport(error: { message?: string; digest?: string }, path: string,
  component: ErrorReport['component'] = 'frontend'): ErrorReport {
  return {
    message: (error.message || 'Unknown error').slice(0, 500),
    digest: (error.digest ?? '').slice(0, 100),
    path: path.split('?')[0].split('#')[0].slice(0, 300),
    component,
  };
}

export function reportError(error: { message?: string; digest?: string }) {
  if (typeof window === 'undefined') return;
  const api = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  const body = JSON.stringify(buildReport(error, window.location.pathname));
  try {
    // keepalive: звіт іде, навіть якщо користувач одразу перейде на іншу сторінку.
    void fetch(`${api}${ENDPOINT}`, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/json' },
      keepalive: true,
      credentials: 'omit',
    }).catch(() => undefined);
  } catch {
    // звіт про помилку не повинен сам ламати сторінку
  }
}
