/**
 * Серверний редірект гостя з закритих сторінок (08-S7, задача 6.2).
 *
 * Перевіряється ТІЛЬКИ наявність cookie `has_session` (мітка сесії з 1.4, живе стільки ж,
 * скільки refresh). Права й валідність токена proxy не перевіряє — це робить API (401/403)
 * і useRequireAuth на клієнті. По `access` не перевіряємо: він живе 15 хвилин.
 *
 * Список маршрутів тримати в одному наборі з PRIVATE_PATHS у e2e/private-pages.spec.ts.
 * Модулі /b2b і /dealers/apply заморожені (404 за флагами 2.8) — у matcher не входять: гостю там потрібен 404, а не 307.
 * Публічні маршрути, /_next/*, /api/*, статика в matcher не входять.
 */
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function proxy(request: NextRequest) {
  // Та сама умова, що й на клієнті (lib/session-hint.ts): підказка лише при значенні '1'.
  if (request.cookies.get('has_session')?.value === '1') return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  // Абсолютний URL від request.nextUrl (хост із заголовка Host, nginx передає $host): Next сам
  // робить Location відносним для того ж хоста. Відносний рядок у Location ламає proxy (Invalid URL).
  // next збирається з pathname запиту, тож зовнішня адреса туди потрапити не може.
  const url = request.nextUrl.clone();
  url.pathname = '/login';
  url.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url, 307);
}

export const config = {
  matcher: [
    '/me',
    '/me/:path*',
    '/local/new',
    '/local/:id/edit',
  ],
};
