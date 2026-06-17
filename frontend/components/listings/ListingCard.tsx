import Link from 'next/link';
import Image from 'next/image';
import { Listing } from '@/lib/types';
import Badge from '@/components/ui/Badge';

const STATUS_LABELS: Record<string, { label: string; variant: 'info' | 'success' | 'default' }> = {
  in_transit: { label: 'В пути', variant: 'info' },
  in_stock: { label: 'В наличии', variant: 'success' },
  sold: { label: 'Продан', variant: 'default' },
};

const FUEL_LABELS: Record<string, string> = {
  petrol: 'Бензин', diesel: 'Дизель', electric: 'Электро', hybrid: 'Гибрид',
};

export default function ListingCard({ listing }: { listing: Listing }) {
  const v = listing.vehicle_detail;
  const st = STATUS_LABELS[listing.status] ?? { label: listing.status, variant: 'default' };
  const primaryImg = v.images.find(i => i.is_primary) ?? v.images[0];
  const imgSrc = primaryImg?.image ?? null;

  return (
    <Link href={`/listings/${listing.id}`} className="block group">
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md hover:border-blue-300 transition-all">
        {/* Photo */}
        <div className="relative h-48 bg-slate-100">
          {imgSrc ? (
            <Image src={imgSrc} alt={`${v.make} ${v.model}`} fill className="object-cover" />
          ) : (
            <div className="flex items-center justify-center h-full text-slate-300 text-5xl">🚗</div>
          )}
          <div className="absolute top-2 left-2 flex gap-1">
            <Badge variant={st.variant}>{st.label}</Badge>
            {listing.is_express_active && (
              <Badge variant="danger">🔥 Срочный выкуп</Badge>
            )}
          </div>
        </div>

        {/* Info */}
        <div className="p-4">
          <p className="font-bold text-slate-900 text-lg group-hover:text-blue-700 transition-colors truncate">
            {v.year} {v.make} {v.model}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            {FUEL_LABELS[v.fuel_type]} · {(v.engine_cc / 1000).toFixed(1)}L · {v.mileage_km.toLocaleString()} км
          </p>
          {v.damage_type && (
            <p className="text-xs text-amber-700 mt-1 truncate">Повреждение: {v.damage_type}</p>
          )}
          <div className="mt-3 flex items-baseline gap-1">
            <span className="text-2xl font-extrabold text-blue-800">
              {Number(listing.price).toLocaleString()}
            </span>
            <span className="text-sm font-semibold text-blue-600">{listing.currency}</span>
          </div>
        </div>
      </div>
    </Link>
  );
}
