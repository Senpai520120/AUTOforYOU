import Link from 'next/link';
import Image from 'next/image';
import { LocalListing } from '@/lib/types';

const FUEL_LABELS: Record<string, string> = {
  petrol: 'Бензин', diesel: 'Дизель', electric: 'Електро', hybrid: 'Гібрид', gas: 'Газ',
};
const TRANSMISSION_LABELS: Record<string, string> = {
  auto: 'Автомат', manual: 'Механіка', cvt: 'Варіатор', robot: 'Робот',
};

const PLACEHOLDER_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='280' viewBox='0 0 400 280'%3E%3Crect width='400' height='280' fill='%23e2e8f0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='14' fill='%2394a3b8'%3EФото відсутнє%3C/text%3E%3C/svg%3E";

export default function LocalListingCard({ listing }: { listing: LocalListing }) {
  const primary = listing.images.find((i) => i.is_primary) ?? listing.images[0];
  const imgSrc = primary?.image || primary?.source_url || PLACEHOLDER_SVG;

  const price = Number(listing.price).toLocaleString('uk-UA');

  return (
    <article className="bg-white rounded-xl overflow-hidden shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
      <Link href={`/local/${listing.id}`} className="block relative aspect-[4/3]">
        <Image
          src={imgSrc}
          alt={`${listing.make} ${listing.model} ${listing.year}`}
          fill
          className="object-cover"
          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
          onError={(e) => { (e.currentTarget as HTMLImageElement).src = PLACEHOLDER_SVG; }}
        />
      </Link>
      <div className="p-4">
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
        <div className="mt-1 text-xs text-slate-400">
          {listing.city_name}, {listing.region_name}
        </div>
        <div className="mt-2 flex items-center justify-between">
          <span className="font-bold text-slate-900">
            {price} {listing.currency}
            {listing.price_type === 'negotiable' && (
              <span className="ml-1 text-xs font-normal text-slate-500">торг</span>
            )}
          </span>
        </div>
      </div>
    </article>
  );
}
