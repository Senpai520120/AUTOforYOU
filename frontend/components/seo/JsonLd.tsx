import { jsonLdString, type JsonLd as JsonLdData } from '@/lib/jsonld';

/**
 * Структуровані дані сторінки (9.54). Серверний компонент: розмітка є в першій відповіді HTML.
 * Тип application/ld+json браузер не виконує, тож CSP script-src не зачіпається.
 */
export default function JsonLd({ data }: { data: JsonLdData | JsonLdData[] | null }) {
  if (!data) return null;
  const list = Array.isArray(data) ? data : [data];
  return (
    <>
      {list.map((item, i) => (
        <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdString(item) }} />
      ))}
    </>
  );
}
