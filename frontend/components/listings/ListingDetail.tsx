'use client';
import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { Listing } from '@/lib/types';
import Badge from '@/components/ui/Badge';

const FUEL: Record<string, string> = {
  petrol: 'Бензин', diesel: 'Дизель', electric: 'Електро', hybrid: 'Гібрид',
};

export default function ListingDetail({ listing }: { listing: Listing }) {
  const v = listing.vehicle_detail;
  const imgs = v.images;
  const [imgIdx, setImgIdx] = useState(0);

  const currentImg = imgs[imgIdx];
  const imgSrc = currentImg?.image || currentImg?.source_url || null;

  return (
    <div>
      <Link href="/listings" className="text-blue-600 text-sm hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 rounded">
        ← Каталог
      </Link>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Gallery */}
        <div>
          <div className="relative h-80 bg-slate-100 rounded-xl overflow-hidden">
            {imgSrc ? (
              <Image
                src={imgSrc}
                alt={`${v.make} ${v.model} ${v.year} — фото`}
                fill
                className="object-cover"
                sizes="(max-width: 1024px) 100vw, 50vw"
                priority
              />
            ) : (
              <div className="flex items-center justify-center h-full text-slate-300" aria-label="Фото відсутнє">
                <svg className="w-24 h-24" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
            )}
          </div>
          {imgs.length > 1 && (
            <div className="flex gap-2 mt-3 flex-wrap" role="group" aria-label="Галерея фото">
              {imgs.map((img, i) => {
                const src = img.image || img.source_url || null;
                return (
                  <button
                    key={img.id}
                    onClick={() => setImgIdx(i)}
                    aria-label={`Фото ${i + 1}`}
                    aria-current={i === imgIdx}
                    className={`relative w-16 h-16 rounded-lg overflow-hidden border-2 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                      i === imgIdx ? 'border-blue-600' : 'border-transparent'
                    }`}
                  >
                    {src && (
                      <Image src={src} alt={`Фото ${i + 1}`} fill className="object-cover" sizes="64px" />
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Info */}
        <div>
          <div className="flex items-start gap-3 flex-wrap">
            <h1 className="text-2xl font-extrabold text-slate-900">{v.year} {v.make} {v.model}</h1>
            {listing.is_express_active && <Badge variant="danger">Терміновий викуп</Badge>}
          </div>
          <p className="text-3xl font-extrabold text-blue-800 mt-2">
            {Number(listing.price).toLocaleString('uk-UA')} {listing.currency}
          </p>

          <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            {[
              ['VIN', v.vin],
              ['Паливо', FUEL[v.fuel_type] ?? v.fuel_type],
              ['Двигун', `${(v.engine_cc / 1000).toFixed(1)} л (${v.engine_cc} см³)`],
              ['Пробіг', `${v.mileage_km.toLocaleString('uk-UA')} км`],
              ['Аукціон', v.source_auction.toUpperCase()],
              ['Лот', v.lot_number || '—'],
              ['Пошкодження', v.damage_type || '—'],
              ['Статус', listing.status === 'in_transit' ? 'В дорозі' : listing.status === 'in_stock' ? 'В наявності' : 'Продано'],
            ].map(([label, val]) => (
              <div key={label}>
                <dt className="text-xs text-slate-500 font-semibold uppercase tracking-wide">{label}</dt>
                <dd className="mt-0.5 text-slate-900">{val}</dd>
              </div>
            ))}
          </dl>

          {listing.repair_description && (
            <div className="mt-5 bg-slate-50 border border-slate-200 rounded-lg p-4">
              <p className="text-xs font-semibold text-slate-500 uppercase mb-1">Опис ремонту</p>
              <p className="text-sm text-slate-700 whitespace-pre-wrap">{listing.repair_description}</p>
            </div>
          )}

          <div className="mt-6 flex gap-3 flex-wrap">
            <Link
              href={`/calculator?price=${listing.price}&engine_cc=${v.engine_cc}&fuel_type=${v.fuel_type}&year=${v.year}`}
              className="bg-blue-700 hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 text-white font-semibold px-6 py-2.5 rounded-lg transition-colors text-sm"
            >
              Порахувати вартість
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
