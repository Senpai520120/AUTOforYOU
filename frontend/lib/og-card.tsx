import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ImageResponse } from 'next/og';
import { SITE_NAME } from '@/lib/site';

/**
 * Генерація OG-картинок (задача 6.3b).
 *
 * Шрифт - локальний файл у репозиторії (frontend/assets, Noto Sans, SIL OFL 1.1),
 * з мережі в рантаймі нічого не вантажимо. Кирилиця, включно з Ї Є І Ґ, є в шрифті.
 * Картинка будується лише з публічних полів (марка, модель, рік, ціна): ні телефону, ні контактів.
 */
export const OG_SIZE = { width: 1200, height: 630 } as const;
export const OG_CONTENT_TYPE = 'image/png';

/** Службовий заголовок X-OG-Variant: бренд-заглушка / картка з даними / картка з фото (для тестів). */
export type OgVariant = 'brand' | 'item' | 'photo';

// Не довше, ніж живе сама сторінка (revalidate <= 60 с).
export const ITEM_CACHE = 'public, max-age=60, s-maxage=60';

const apiUrl = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// Окрема змінна: /media/ у проді віддає nginx (том media), а не Django (там лише при DEBUG).
const mediaUrl = process.env.INTERNAL_MEDIA_URL ?? 'http://nginx';
const MAX_PHOTO_BYTES = 4 * 1024 * 1024;
// Лише фото оголошень: інші файли /media/ (трекінг, вкладення) у превью не потрапляють.
const PHOTO_PREFIX = '/media/local_listings/';

const NAVY = '#0b1f3a';
const BLUE = '#1d4ed8';

async function fonts() {
  const [regular, bold] = await Promise.all([
    readFile(join(process.cwd(), 'assets/NotoSans-Regular.ttf')),
    readFile(join(process.cwd(), 'assets/NotoSans-Bold.ttf')),
  ]);
  return [
    { name: 'Noto Sans', data: regular, style: 'normal' as const, weight: 400 as const },
    { name: 'Noto Sans', data: bold, style: 'normal' as const, weight: 700 as const },
  ];
}

/** Рендеримо у буфер одразу, щоб помилку генерації можна було перехопити (fallback), а не віддати обірваний потік. */
async function render(element: React.ReactElement, cacheControl: string, variant: OgVariant): Promise<Response> {
  const img = new ImageResponse(element, { ...OG_SIZE, fonts: await fonts() });
  const body = await img.arrayBuffer();
  return new Response(body, {
    headers: { 'Content-Type': OG_CONTENT_TYPE, 'Cache-Control': cacheControl, 'X-OG-Variant': variant },
  });
}

const PAGE_STYLE = {
  width: '100%',
  height: '100%',
  display: 'flex',
  flexDirection: 'column' as const,
  justifyContent: 'space-between',
  padding: 64,
  color: 'white',
  fontFamily: 'Noto Sans',
  backgroundImage: `linear-gradient(135deg, ${NAVY} 0%, ${BLUE} 100%)`,
};

function Brand() {
  return <div style={{ display: 'flex', fontSize: 40, fontWeight: 700, letterSpacing: 1 }}>{SITE_NAME}</div>;
}

/** Бренд-картинка без жодних цифр: головна, калькулятор, fallback при збої. */
export async function brandCard(
  tagline = 'Авто з США під ключ',
  sub = 'Калькулятор вартості, доставка, розмитнення, оголошення по Україні',
  cacheControl = 'public, max-age=86400, s-maxage=86400',
): Promise<Response> {
  return render(
    <div style={PAGE_STYLE}>
      <Brand />
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', fontSize: 88, fontWeight: 700, lineHeight: 1.1 }}>{tagline}</div>
        <div style={{ display: 'flex', fontSize: 34, marginTop: 24, opacity: 0.85 }}>{sub}</div>
      </div>
      <div style={{ display: 'flex', fontSize: 28, opacity: 0.7 }}>Copart · IAAI · Україна</div>
    </div>,
    cacheControl,
    'brand',
  );
}

export interface ItemCardData {
  title: string;
  /** Уже відформатована ціна з валютою об'єкта, без перерахунку за курсом. */
  price: string;
  label: string;
  /** data:-URL фото (лише для місцевих оголошень). */
  photo?: string | null;
}

function titleSize(title: string): number {
  if (title.length <= 20) return 84;
  if (title.length <= 32) return 66;
  return 52;
}

/** Картка лота/оголошення: марка, модель, рік, ціна; з фото або без. */
export async function itemCard({ title, price, label, photo }: ItemCardData): Promise<Response> {
  return render(
    <div style={{ ...PAGE_STYLE, padding: 0, flexDirection: 'row' }}>
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: 64, flex: 1 }}>
        <Brand />
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', fontSize: 30, opacity: 0.8, marginBottom: 16 }}>{label}</div>
          <div style={{ display: 'flex', fontSize: titleSize(title), fontWeight: 700, lineHeight: 1.1, maxHeight: 300, overflow: 'hidden' }}>
            {title}
          </div>
          <div style={{ display: 'flex', fontSize: 64, fontWeight: 700, marginTop: 32 }}>{price}</div>
        </div>
        <div style={{ display: 'flex', fontSize: 26, opacity: 0.7 }}>Детальніше на {SITE_NAME}</div>
      </div>
      {photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photo} alt="" width={460} height={630} style={{ width: 460, height: 630, objectFit: 'cover' }} />
      ) : null}
    </div>,
    ITEM_CACHE,
    photo ? 'photo' : 'item',
  );
}

/**
 * Фото оголошення як data-URL. Тягнемо тільки з INTERNAL_MEDIA_URL (хост фіксований: SSRF неможливий),
 * лише шлях /media/local_listings/, без редіректів, з таймаутом; jpeg/png до 4 МБ. Інше - без фото.
 */
export async function loadMediaPhoto(rawUrl: string | null | undefined): Promise<string | null> {
  if (!rawUrl) return null;
  try {
    const path = new URL(rawUrl, 'http://placeholder.invalid').pathname;
    if (!path.startsWith(PHOTO_PREFIX) || path.includes('..')) return null;
    const res = await fetch(`${mediaUrl}${path}`, {
      redirect: 'error',
      signal: AbortSignal.timeout(3000),
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    const type = (res.headers.get('content-type') ?? '').split(';')[0].trim();
    if (type !== 'image/jpeg' && type !== 'image/png') return null;
    // Великий файл відхиляємо до читання тіла.
    if (Number(res.headers.get('content-length') ?? 0) > MAX_PHOTO_BYTES) return null;
    const buf = await res.arrayBuffer();
    if (buf.byteLength === 0 || buf.byteLength > MAX_PHOTO_BYTES) return null;
    return `data:${type};base64,${Buffer.from(buf).toString('base64')}`;
  } catch {
    return null;
  }
}

export const notFoundResponse = () => new Response(null, { status: 404 });

/** 'missing' - 404 API, 'error' - збій/мережа, 'ok' - дані. */
export async function fetchPublicJson<T>(
  path: string,
  revalidate = 60,
): Promise<{ kind: 'ok'; data: T } | { kind: 'missing' } | { kind: 'error' }> {
  try {
    const res = await fetch(`${apiUrl}${path}`, { next: { revalidate } });
    if (res.status === 404) return { kind: 'missing' };
    if (!res.ok) return { kind: 'error' };
    return { kind: 'ok', data: (await res.json()) as T };
  } catch {
    return { kind: 'error' };
  }
}
