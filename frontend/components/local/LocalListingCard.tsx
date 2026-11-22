'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { isLocalMediaUrl } from '@/lib/media';
import { LocalListing } from '@/lib/types';
import ChannelBadge from '@/components/local/ChannelBadge';
import { VERIFIED_DEALER_LABEL } from '@/lib/labels';
import { formatUsd } from '@/lib/format';
import { Gauge, Fuel, Settings2, MapPin } from 'lucide-react';
import { Card } from '@/components/shadcn/card';
import { ICON_STROKE } from '@/lib/utils';

const FUEL_LABELS: Record<string, string> = {
  petrol: 'Бензин', diesel: 'Дизель', electric: 'Електро', hybrid: 'Гібрид', gas: 'Газ',
};
const TRANSMISSION_LABELS: Record<string, string> = {
  auto: 'Автомат', manual: 'Механіка', cvt: 'Варіатор', robot: 'Робот',
};

const PLACEHOLDER_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='280' viewBox='0 0 400 280'%3E%3Crect width='400' height='280' fill='%23e2e8f0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='14' fill='%23475569'%3EФото відсутнє%3C/text%3E%3C/svg%3E";

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

  const meta = [
    { key: 'fuel', Icon: Fuel, text: FUEL_LABELS[listing.fuel_type] ?? listing.fuel_type },
    { key: 'tr', Icon: Settings2, text: TRANSMISSION_LABELS[listing.transmission] ?? listing.transmission },
    { key: 'km', Icon: Gauge, text: `${listing.mileage_km.toLocaleString()} км` },
  ];

  return (
    <article className="h-full">
      <Card className={`group h-full gap-0 overflow-hidden py-0 transition-shadow hover:shadow-md ${isTop ? 'border-accent ring-1 ring-accent' : ''}`}>
        <Link href={`/local/${listing.id}`} className="relative block aspect-[4/3] bg-muted">
          <Image
            src={imgSrc}
            alt={`${listing.make} ${listing.model} ${listing.year}`}
            fill
            {...(priority ? { loading: 'eager', fetchPriority: 'high' } as const : {})}
            className="object-cover"
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            unoptimized={isLocalMediaUrl(imgSrc)}
            onError={() => setFailedSrc(original)}
          />
          {isTop && (
            <span className="absolute top-2 left-2 rounded-full bg-accent px-2.5 py-0.5 text-xs font-bold text-accent-foreground shadow">
              ТОП
            </span>
          )}
        </Link>
        <div className="flex flex-1 flex-col p-4">
          {(listing.source_channel || listing.seller_type === 'dealer') && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              <ChannelBadge channel={listing.source_channel} />
              {listing.seller_type === 'dealer' && (
                <span data-testid="verified-dealer" className="inline-block rounded-full bg-link/10 px-2 py-0.5 text-xs font-semibold text-link">
                  ✓ {VERIFIED_DEALER_LABEL}
                </span>
              )}
            </div>
          )}
          <Link href={`/local/${listing.id}`} className="hover:text-link">
            <h2 className="text-base font-semibold leading-snug text-foreground">
              {listing.make} {listing.model} {listing.year}
            </h2>
          </Link>
          <div className="mt-2 flex items-baseline gap-x-2 flex-wrap">
            <span className="text-xl font-bold text-foreground">
              {price} {listing.currency}
            </span>
            {/* 10.24: орієнтир у $ за курсом на момент збереження; для USD не дублюємо. */}
            {listing.currency !== 'USD' && listing.price_usd && (
              <span data-testid="price-usd" className="text-xs font-normal text-muted-foreground">
                ≈ {formatUsd(listing.price_usd, 0)}
              </span>
            )}
            {listing.price_type === 'negotiable' && (
              <span className="text-xs font-normal text-muted-foreground">торг</span>
            )}
          </div>
          <ul className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {meta.map(({ key, Icon, text }) => (
              <li key={key} className="inline-flex items-center gap-1">
                <Icon className="size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
                {key === 'fuel' && listing.engine_cc ? `${text}, ${(listing.engine_cc / 1000).toFixed(1)} л` : text}
              </li>
            ))}
          </ul>
          <p className="mt-auto inline-flex items-center gap-1 pt-3 text-xs text-muted-foreground">
            <MapPin className="size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
            {listing.city_name}, {listing.region_name}
          </p>
        </div>
      </Card>
    </article>
  );
}
