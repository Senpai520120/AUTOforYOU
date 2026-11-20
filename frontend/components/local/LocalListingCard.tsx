'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { LocalListing } from '@/lib/types';
import ChannelBadge from '@/components/local/ChannelBadge';
import { VERIFIED_DEALER_LABEL } from '@/lib/labels';
import { formatUsd } from '@/lib/format';

const FUEL_LABELS: Record<string, string> = {
  petrol: 'Бензин', diesel: 'Дизель', electric: 'Електро', hybrid: 'Гібрид', gas: 'Газ',
};
const TRANSMISSION_LABELS: Record<string, string> = {
  auto: 'Автомат', manual: 'Механіка', cvt: 'Варіатор', robot: 'Робот',
};

const PLACEHOLDER_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='280' viewBox='0 0 400 280'%3E%3Crect width='400' height='280' fill='%23e2e8f0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='14' fill='%2394a3b8'%3EФото відсутнє%3C/text%3E%3C/svg%3E";

/** priority — перше зображення сторінки: вантажиться одразу, без lazy (LCP). */
export default function LocalListingCard({ listing, priority = false }: { listing: LocalListing; priority?: boolean }) {
  const primary = listing.images.find((i) => i.is_primary) ?? listing.images[0];
  // 8.4: у списку — мініатюра; оригінал лише на сторінці оголошення.
  const original = primary?.thumbnail || primary?.image || primary?.source_url || PLACEHOLDER_SVG;
  // 10.3: заглушка через state. Пряма заміна currentTarget.src скидалась ре-рендером React → цикл запитів.
  // Зберігаємо саме адресу, що впала: при зміні фото (інший src) заглушка скидається.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const imgSrc = failedSrc === original ? PLACEHOLDER_SVG : original;

  const price = Number(listing.price).toLocaleString('uk-UA');
  const isTop = listing.promoted_until && new Date(listing.promoted_until) > new Date();

  return (
    <article className={`bg-white rounded-xl overflow-hidden shadow-sm border transition-shadow hover:shadow-md ${isTop ? 'border-amber-300 ring-1 ring-amber-200' : 'border-slate-100'}`}>
      <Link href={`/local/${listing.id}`} className="block relative aspect-[4/3]">
        <Image
          src={imgSrc}
          alt={`${listing.make} ${listing.model} ${listing.year}`}
          fill
          {...(priority ? { loading: 'eager', fetchPriority: 'high' } as const : {})}
          className="object-cover"
          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
          onError={() => setFailedSrc(original)}
        />
        {isTop && (
          <span className="absolute top-2 left-2 bg-amber-400 text-black text-[11px] font-bold px-2 py-0.5 rounded-full shadow">
            ТОП
          </span>
        )}
      </Link>
      <div className="p-4">
        <ChannelBadge channel={listing.source_channel} className="mb-2" />
        {listing.seller_type === 'dealer' && (
          <span data-testid="verified-dealer" className="mb-2 mr-1 inline-block text-[11px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-semibold">
            ✓ {VERIFIED_DEALER_LABEL}
          </span>
        )}
        <Link href={`/local/${listing.id}`} className="hover:text-blue-700">
          <h2 className="font-semibold text-slate-900 text-sm leading-snug">
            {listing.make} {listing.model} {listing.year}
          </h2>
        </Link>
        <div className="mt-1 flex flex-wrap gap-1 text-xs text-slate-500">
          <span>{FUEL_LABELS[listing.fuel_type] ?? listing.fuel_type}</span>
          <span>·</span>
          <span>{TRANSMISSION_LABELS[listing.transmission] ?? listing.transmission}</span>
          {listing.engine_cc && (
            <>
              <span>·</span>
              <span>{(listing.engine_cc / 1000).toFixed(1)} л</span>
            </>
          )}
          <span>·</span>
          <span>{listing.mileage_km.toLocaleString()} км</span>
        </div>
        <div className="mt-1 text-xs text-slate-600">
          {listing.city_name}, {listing.region_name}
        </div>
        <div className="mt-2 flex items-center justify-between">
          <span className="font-bold text-slate-900">
            {price} {listing.currency}
            {/* 10.24: орієнтир у $ за курсом на момент збереження; для USD не дублюємо. */}
            {listing.currency !== 'USD' && listing.price_usd && (
              <span data-testid="price-usd" className="ml-1 text-xs font-normal text-slate-500">
                ≈ {formatUsd(listing.price_usd, 0)}
              </span>
            )}
            {listing.price_type === 'negotiable' && (
              <span className="ml-1 text-xs font-normal text-slate-500">торг</span>
            )}
          </span>
        </div>
      </div>
    </article>
  );
}
