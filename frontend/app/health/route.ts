/**
 * Healthcheck контейнера frontend (задача 7.3): живість процесу Next без звернення до backend.
 * Публічні сторінки навмисно не використовуються: їхній рендер залежить від API.
 */
export const dynamic = 'force-dynamic';

export function GET() {
  return new Response('ok', { status: 200, headers: { 'Cache-Control': 'no-store' } });
}
