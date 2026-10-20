import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// 2.8: сторінки заморожених модулів — справжній 404 ще до рендеру. Layout-перевірка (requireModule) лишається
// другою лінією, але сама не дає статусу 404 там, де батьківський loading.tsx уже почав стрімінг (/me).
const apiUrl = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const FROZEN: [RegExp, string][] = [
  [/^\/listings(\/|$)/, 'lots_enabled'],
  [/^\/b2b(\/|$)/, 'b2b_enabled'],
  [/^\/dealers(\/|$)/, 'dealers_enabled'],
  [/^\/me\/shipments(\/|$)/, 'shipments_enabled'],
];

// Кеш прапорів на 30 с у пам'яті процесу: без нього кожен запит/префетч замороженої сторінки йде в API.
let cached: { at: number; flags: Record<string, unknown> | null } | null = null;
const TTL_MS = 30_000;

async function moduleFlags(): Promise<Record<string, unknown> | null> {
  if (cached && Date.now() - cached.at < TTL_MS) return cached.flags;
  let flags: Record<string, unknown> | null = null;  // недоступні налаштування = «вимкнено»
  try {
    const res = await fetch(`${apiUrl}/api/v1/site-settings/`, { cache: 'no-store' });
    if (res.ok) flags = await res.json();
  } catch {
    flags = null;
  }
  cached = { at: Date.now(), flags };
  return flags;
}

export async function proxy(request: NextRequest) {
  const flag = FROZEN.find(([re]) => re.test(request.nextUrl.pathname))?.[1];
  if (!flag) return NextResponse.next();
  const enabled = (await moduleFlags())?.[flag] === true;
  if (enabled) return NextResponse.next();
  return NextResponse.rewrite(new URL('/__frozen-module-not-found', request.url));
}

export const config = {
  matcher: ['/listings', '/listings/:path*', '/b2b', '/b2b/:path*', '/dealers/:path*', '/me/shipments/:path*', '/me/shipments'],
};
