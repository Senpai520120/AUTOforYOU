/**
 * Фото з локального хоста (dev/e2e: http://localhost/media/...) не можна віддавати через /_next/image:
 * Next 16 забороняє оптимізатору локальні IP ("url" parameter is not allowed), а в контейнері
 * frontend localhost:80 — це він сам. Такі фото йдуть у `<Image unoptimized>`: браузер бере їх
 * напряму через nginx. Прод (домен/S3/R2) лишається на оптимізаторі; налаштування images у
 * next.config.ts (захист від SSRF) не змінюються.
 */
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

export function isLocalMediaUrl(src: unknown): boolean {
  if (typeof src !== 'string' || !src) return false;
  if (src.startsWith('/') && !src.startsWith('//')) return src.startsWith('/media/');
  try {
    return LOCAL_HOSTS.has(new URL(src).hostname);
  } catch {
    return false;
  }
}
