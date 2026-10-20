/**
 * Помилки серверного рендеру Next (SSR, route handlers) — у моніторинг через бекенд (задача 7.6).
 * Той самий мінімальний звіт, що й з браузера: повідомлення, digest, шлях без query.
 */
import type { Instrumentation } from 'next';
import { buildReport } from './lib/reportError';

export const onRequestError: Instrumentation.onRequestError = async (err, request) => {
  const api = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  const error = err as { message?: string; digest?: string };
  try {
    await fetch(`${api}/api/v1/monitoring/client-errors/`, {
      method: 'POST',
      body: JSON.stringify(buildReport(error, request.path, 'frontend-ssr')),
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    // мониторинг недоступний — рендер помилки не ламаємо
  }
};
