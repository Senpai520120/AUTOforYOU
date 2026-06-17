'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Image from 'next/image';
import { listingsApi } from '@/api/listings';
import { Listing } from '@/lib/types';
import Badge from '@/components/ui/Badge';
import Spinner from '@/components/ui/Spinner';
import Link from 'next/link';

const FUEL: Record<string, string> = { petrol: 'Бензин', diesel: 'Дизель', electric: 'Електро', hybrid: 'Гібрид' };

export default function ListingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [imgIdx, setImgIdx] = useState(0);

  useEffect(() => {
    listingsApi.detail(Number(id)).then(setListing).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>;
  if (!listing) return <p className="text-center py-20 text-slate-500">Оголошення не знайдено</p>;

  const v = listing.vehicle_detail;
  const imgs = v.images;

  return (
    <div>
      <Link href="/listings" className="text-blue-600 text-sm hover:underline">← Каталог</Link>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Gallery */}
        <div>
          <div className="relative h-80 bg-slate-100 rounded-xl overflow-hidden">
            {imgs[imgIdx] ? (
              <Image src={imgs[imgIdx].image} alt={`${v.make} ${v.model}`} fill className="object-cover" />
            ) : (
              <div className="flex items-center justify-center h-full text-6xl text-slate-300">🚗</div>
            )}
          </div>
          {imgs.length > 1 && (
            <div className="flex gap-2 mt-3 flex-wrap">
              {imgs.map((img, i) => (
                <button key={img.id} onClick={() => setImgIdx(i)}
                  className={`relative w-16 h-16 rounded-lg overflow-hidden border-2 transition-colors ${i === imgIdx ? 'border-blue-600' : 'border-transparent'}`}>
                  <Image src={img.image} alt="" fill className="object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Info */}
        <div>
          <div className="flex items-start gap-3 flex-wrap">
            <h1 className="text-2xl font-extrabold text-slate-900">{v.year} {v.make} {v.model}</h1>
            {listing.is_express_active && <Badge variant="danger">🔥 Срочный выкуп</Badge>}
          </div>
          <p className="text-3xl font-extrabold text-blue-800 mt-2">
            {Number(listing.price).toLocaleString()} {listing.currency}
          </p>

          <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            {[
              ['VIN', v.vin],
              ['Паливо', FUEL[v.fuel_type]],
              ['Двигун', `${(v.engine_cc / 1000).toFixed(1)} л (${v.engine_cc} см³)`],
              ['Пробіг', `${v.mileage_km.toLocaleString()} км`],
              ['Аукціон', v.source_auction.toUpperCase()],
              ['Лот', v.lot_number || '—'],
              ['Пошкодження', v.damage_type || '—'],
              ['Статус', listing.status],
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

          <div className="mt-6 flex gap-3">
            <Link
              href={`/calculator?price=${listing.price}&engine_cc=${v.engine_cc}&fuel_type=${v.fuel_type}&year=${v.year}`}
              className="bg-blue-700 hover:bg-blue-800 text-white font-semibold px-6 py-2.5 rounded-lg transition-colors text-sm"
            >
              Порахувати вартість
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
