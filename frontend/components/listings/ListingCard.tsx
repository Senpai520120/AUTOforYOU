import Link from 'next/link';
import Image from 'next/image';
import { Listing } from '@/lib/types';
import { listingSlug } from '@/lib/utils';
import Badge from '@/components/ui/Badge';

const STATUS_LABELS: Record<string, { label: string; variant: 'info' | 'success' | 'default' }> = {
  in_transit: { label: 'В дорозі', variant: 'info' },
  in_stock:   { label: 'В наявності', variant: 'success' },
  sold:       { label: 'Продано', variant: 'default' },
};

const FUEL_LABELS: Record<string, string> = {
  petrol: 'Бензин', diesel: 'Дизель', electric: 'Електро', hybrid: 'Гібрид',
};

export default function ListingCard({ listing }: { listing: Listing }) {
  const v = listing.vehicle_detail;
  const st = STATUS_LABELS[listing.status] ?? { label: listing.status, variant: 'default' as const };
  const primaryImg = v.images.find(i => i.is_primary) ?? v.images[0];
  // Prefer stored media file; fall back to external source_url from lot import
  const imgSrc = primaryImg?.image || primaryImg?.source_url || null;
  const altText = `${v.year} ${v.make} ${v.model}`;

  return (
    <Link href={`/listings/${listingSlug(listing)}`} className="block group focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-xl">
      <article className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md hover:border-blue-300 transition-all">
        {/* Photo */}
        <div className="relative h-48 bg-slate-100">
          {imgSrc ? (
            <Image
              src={imgSrc}
              alt={altText}
              fill
              className="object-cover"
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
            />
          ) : (
            <div className="flex items-center justify-center h-full text-slate-300" aria-label="Фото відсутнє">
              <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
          )}
          <div className="absolute top-2 left-2 flex gap-1">
            <Badge variant={st.variant}>{st.label}</Badge>
            {listing.is_express_active && (
              <Badge variant="danger">Терміновий викуп</Badge>
            )}
          </div>
        </div>

        {/* Info */}
        <div className="p-4">
          <p className="font-bold text-slate-900 text-lg group-hover:text-blue-700 transition-colors truncate">
            {v.year} {v.make} {v.model}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            {FUEL_LABELS[v.fuel_type] ?? v.fuel_type} · {(v.engine_cc / 1000).toFixed(1)}L · {v.mileage_km.toLocaleString('uk-UA')} км
          </p>
          {v.damage_type && (
            <p className="text-xs text-amber-700 mt-1 truncate">Пошкодження: {v.damage_type}</p>
          )}
          <div className="mt-3 flex items-baseline gap-1">
            <span className="text-2xl font-extrabold text-blue-800">
              {Number(listing.price).toLocaleString('uk-UA')}
            </span>
            <span className="text-sm font-semibold text-blue-600">{listing.currency}</span>
          </div>
        </div>
      </article>
    </Link>
  );
}
