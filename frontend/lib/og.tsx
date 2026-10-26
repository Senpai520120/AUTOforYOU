// OG/Twitter-превью (задача 6.3b): бренд-картка та картка оголошення. Генерується на сервері Next (ImageResponse).
// Шрифт з кирилицею — у репозиторії (assets/fonts, DejaVu Sans, ліцензія Bitstream Vera поруч).
// У картку йдуть лише публічні поля (марка, модель, рік, ціна, місто) — телефонів і контактів тут немає в принципі.
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ImageResponse } from 'next/og';
import { SITE_NAME } from '@/lib/site';

export const OG_SIZE = { width: 1200, height: 630 };
export const OG_CONTENT_TYPE = 'image/png';
export const BRAND_ALT = `${SITE_NAME} — пригін авто з США під ключ`;

const PHOTO_MAX_BYTES = 2_000_000;
const PHOTO_TIMEOUT_MS = 3000;

async function fonts() {
  const dir = join(process.cwd(), 'assets', 'fonts');
  const [regular, bold] = await Promise.all([
    readFile(join(dir, 'DejaVuSans.ttf')),
    readFile(join(dir, 'DejaVuSans-Bold.ttf')),
  ]);
  return [
    { name: 'DejaVu Sans', data: regular, weight: 400 as const, style: 'normal' as const },
    { name: 'DejaVu Sans', data: bold, weight: 700 as const, style: 'normal' as const },
  ];
}

/** Ціна у валюті самого об'єкта, без перерахунку за курсом. */
export function formatPrice(price: string | number, currency: string): string {
  const n = Number(price);
  return Number.isFinite(n) ? `${n.toLocaleString('uk-UA')} ${currency}` : '';
}

/** Фото як data URI — лише невелике зображення, що встигло завантажитися; інакше картка без фото. */
export async function photoDataUri(url: string | null | undefined): Promise<string | null> {
  if (!url || !/^https?:\/\//.test(url)) return null;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(PHOTO_TIMEOUT_MS) });
    const type = res.headers.get('content-type') ?? '';
    if (!res.ok || !/^image\/(jpeg|png|webp)$/.test(type.split(';')[0].trim())) return null;
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.byteLength > PHOTO_MAX_BYTES) return null;
    return `data:${type.split(';')[0].trim()};base64,${buf.toString('base64')}`;
  } catch {
    return null;
  }
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      width: '100%', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      background: 'linear-gradient(135deg, #1e3a8a 0%, #172554 100%)', color: 'white', padding: 64,
      fontFamily: 'DejaVu Sans',
    }}>
      {children}
      <div style={{ display: 'flex', fontSize: 36, fontWeight: 700 }}>
        <span style={{ color: '#fbbf24' }}>AUTO</span><span>forYOU</span>
      </div>
    </div>
  );
}

/** Бренд-картка без цифр ставок — головна, калькулятор і всі сторінки без власного превʼю. */
export async function brandImage(): Promise<ImageResponse> {
  return new ImageResponse(
    (
      <Frame>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <div style={{ fontSize: 72, fontWeight: 700, lineHeight: 1.1 }}>Пригін авто з США під ключ</div>
          <div style={{ fontSize: 36, color: '#bfdbfe' }}>Калькулятор вартості: аукціон, доставка, розмитнення</div>
        </div>
      </Frame>
    ),
    { ...OG_SIZE, fonts: await fonts() },
  );
}

export interface ListingCardInput {
  title: string;     // «Toyota Camry 2020»
  price: string;     // уже відформатована, у валюті обʼєкта
  subtitle?: string; // місто / «Авто з США»
  photo?: string | null;  // data URI
}

/** Картка оголошення/лота. Будь-яка помилка генерації — бренд-картка (200), а не 500.
 *  ImageResponse рендерить ліниво, тож буферизуємо всередині try, щоб помилку рендеру теж перехопити. */
export async function listingImage(input: ListingCardInput): Promise<Response> {
  try {
    const font = await fonts();
    const image = new ImageResponse(
      (
        <Frame>
          <div style={{ display: 'flex', gap: 40, alignItems: 'center' }}>
            {input.photo && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={input.photo} width={480} height={360} alt=""
                style={{ objectFit: 'cover', borderRadius: 24 }} />
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20, flex: 1 }}>
              <div style={{ fontSize: input.photo ? 52 : 68, fontWeight: 700, lineHeight: 1.1 }}>{input.title}</div>
              {input.price && <div style={{ fontSize: 56, fontWeight: 700, color: '#fbbf24' }}>{input.price}</div>}
              {input.subtitle && <div style={{ fontSize: 32, color: '#bfdbfe' }}>{input.subtitle}</div>}
            </div>
          </div>
        </Frame>
      ),
      { ...OG_SIZE, fonts: font },
    );
    const body = await image.arrayBuffer();
    return new Response(body, { headers: { 'content-type': OG_CONTENT_TYPE, 'cache-control': image.headers.get('cache-control') ?? '' } });
  } catch {
    return brandImage();
  }
}

export function notFoundImage(): Response {
  return new Response(null, { status: 404 });
}
