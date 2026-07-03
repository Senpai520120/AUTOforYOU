'use client';
import Image from 'next/image';
import Link from 'next/link';
import { useState } from 'react';
import { LocalListing } from '@/lib/types';
import { useAuth } from '@/lib/auth-context';
import { localApi } from '@/api/local';
import WriteSellerButton from '@/components/messaging/WriteSellerButton';
import HeartButton from '@/components/favorites/HeartButton';
import ReportButton from '@/components/reports/ReportButton';

const PLACEHOLDER_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='800' height='600' viewBox='0 0 800 600'%3E%3Crect width='800' height='600' fill='%23e2e8f0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='18' fill='%2394a3b8'%3EФото відсутнє%3C/text%3E%3C/svg%3E";

const FUEL_LABELS: Record<string, string> = {
  petrol: 'Бензин', diesel: 'Дизель', electric: 'Електро', hybrid: 'Гібрид', gas: 'Газ',
};
const TRANSMISSION_LABELS: Record<string, string> = {
  auto: 'Автомат', manual: 'Механіка', cvt: 'Варіатор', robot: 'Робот',
};
const BODY_LABELS: Record<string, string> = {
  sedan: 'Седан', suv: 'Позашляховик', hatchback: 'Хетчбек', wagon: 'Універсал',
  coupe: 'Купе', minivan: 'Мінівен', pickup: 'Пікап', convertible: 'Кабріолет', other: 'Інше',
};
const CONDITION_LABELS: Record<string, string> = {
  new: 'Новий', used: 'Вживаний', damaged: 'Пошкоджений',
};

export default function LocalListingDetail({ listing }: { listing: LocalListing }) {
  const { user } = useAuth();
  const [activeImg, setActiveImg] = useState(0);
  const [phone, setPhone] = useState<string | null>(null);
  const [phoneLoading, setPhoneLoading] = useState(false);
  const [phoneError, setPhoneError] = useState('');

  const images = listing.images.length > 0 ? listing.images : [{ id: 0, image: null, source_url: '', is_primary: true }];
  const mainImg = images[activeImg]?.image || images[activeImg]?.source_url || PLACEHOLDER_SVG;
  const isOwner = user && listing.owner_name === (user.first_name && user.last_name ? `${user.first_name} ${user.last_name}`.trim() : user.email.split('@')[0]);

  const price = Number(listing.price).toLocaleString('uk-UA');

  const specs = [
    { label: 'Рік', value: listing.year },
    { label: 'Пробіг', value: `${listing.mileage_km.toLocaleString()} км` },
    { label: 'Паливо', value: FUEL_LABELS[listing.fuel_type] ?? listing.fuel_type },
    { label: 'КПП', value: TRANSMISSION_LABELS[listing.transmission] ?? listing.transmission },
    { label: 'Кузов', value: BODY_LABELS[listing.body_type] ?? listing.body_type },
    { label: 'Стан', value: CONDITION_LABELS[listing.condition] ?? listing.condition },
    listing.engine_cc ? { label: "Об'єм двигуна", value: `${(listing.engine_cc / 1000).toFixed(1)} л (${listing.engine_cc} куб.см)` } : null,
  ].filter(Boolean) as { label: string; value: string | number }[];

  const handleShowPhone = async () => {
    if (!user) {
      window.location.href = '/login';
      return;
    }
    setPhoneLoading(true);
    setPhoneError('');
    try {
      const data = await localApi.getContact(listing.id);
      setPhone(data.contact_phone || 'Номер не вказано');
    } catch {
      setPhoneError('Не вдалося завантажити номер. Спробуйте ще раз.');
    } finally {
      setPhoneLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
        <Link href="/ua" className="hover:text-blue-700">Каталог Україна</Link>
        <span>/</span>
        <span>{listing.make} {listing.model}</span>
      </div>

      <div className="flex justify-end mb-2">
        <HeartButton listingType="local" listingId={listing.id} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Gallery */}
        <div>
          <div className="relative aspect-[4/3] rounded-xl overflow-hidden bg-slate-100">
            <Image
              src={mainImg}
              alt={`${listing.make} ${listing.model} ${listing.year}`}
              fill
              className="object-cover"
              sizes="(max-width: 1024px) 100vw, 50vw"
              priority
              onError={(e) => { (e.currentTarget as HTMLImageElement).src = PLACEHOLDER_SVG; }}
            />
          </div>
          {images.length > 1 && (
            <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
              {images.map((img, i) => (
                <button
                  key={img.id || i}
                  onClick={() => setActiveImg(i)}
                  className={`relative flex-shrink-0 w-16 h-16 rounded overflow-hidden border-2 transition-colors ${i === activeImg ? 'border-blue-600' : 'border-transparent'}`}
                >
                  <Image
                    src={img.image || img.source_url || PLACEHOLDER_SVG}
                    alt={`Фото ${i + 1}`}
                    fill
                    className="object-cover"
                    sizes="64px"
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Info panel */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            {listing.make} {listing.model} {listing.year}
          </h1>
          <div className="mt-1 text-sm text-slate-500">
            {listing.city_name}, {listing.region_name}
          </div>

          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-slate-900">
              {price} {listing.currency}
            </span>
            {listing.price_type === 'negotiable' && (
              <span className="text-slate-500 text-sm">— торг</span>
            )}
          </div>

          <div className="mt-6 bg-slate-50 rounded-xl p-4 space-y-2">
            {specs.map(s => (
              <div key={s.label} className="flex justify-between text-sm">
                <span className="text-slate-500">{s.label}</span>
                <span className="font-medium text-slate-900">{s.value}</span>
              </div>
            ))}
          </div>

          <div className="mt-4 p-4 bg-blue-50 rounded-xl">
            <div className="text-sm text-slate-600 flex flex-wrap items-center gap-1.5">
              <span>Продавець: <strong>{listing.owner_name}</strong></span>
              {listing.seller_type === 'dealer' && (
                <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">Дилер</span>
              )}
              {listing.seller_has_badge && (
                <span className="text-xs bg-green-100 text-green-800 px-1.5 py-0.5 rounded font-semibold">✓ Перевірений продавець</span>
              )}
            </div>
            {listing.seller_has_badge && listing.seller_avg_rating && (
              <div className="mt-1 text-xs text-slate-500 flex items-center gap-1">
                <span className="text-amber-400">{'★'.repeat(Math.round(listing.seller_avg_rating))}{'☆'.repeat(5 - Math.round(listing.seller_avg_rating))}</span>
                <span>{listing.seller_avg_rating.toFixed(1)}</span>
                {listing.seller_deal_count ? <span>· {listing.seller_deal_count} угод</span> : null}
              </div>
            )}
            <div className="mt-3">
              {phone ? (
                <a
                  href={`tel:${phone}`}
                  className="block bg-green-600 hover:bg-green-500 text-white font-semibold py-2.5 rounded-lg text-center transition-colors"
                >
                  {phone}
                </a>
              ) : (
                <button
                  onClick={handleShowPhone}
                  disabled={phoneLoading}
                  className="w-full bg-blue-700 hover:bg-blue-600 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg transition-colors"
                >
                  {phoneLoading ? 'Завантаження...' : user ? 'Показати телефон' : 'Увійдіть, щоб побачити телефон'}
                </button>
              )}
              {phoneError && <p className="mt-1 text-xs text-red-500">{phoneError}</p>}
            </div>
          </div>

          {!isOwner && listing.status === 'active' && (
            <div className="mt-3">
              <WriteSellerButton listingType="local" listingId={listing.id} />
            </div>
          )}

          {isOwner && (
            <div className="mt-3 flex gap-2">
              <Link
                href={`/local/${listing.id}/edit`}
                className="flex-1 border border-blue-600 text-blue-700 hover:bg-blue-50 font-semibold py-2 rounded-lg text-center text-sm transition-colors"
              >
                Редагувати
              </Link>
            </div>
          )}

          {!isOwner && (
            <div className="mt-3 flex justify-end">
              <ReportButton listingId={listing.id} />
            </div>
          )}
        </div>
      </div>

      {listing.description && (
        <div className="mt-8">
          <h2 className="font-semibold text-slate-900 mb-2">Опис</h2>
          <div className="bg-white border border-slate-100 rounded-xl p-4 text-sm text-slate-700 whitespace-pre-line">
            {listing.description}
          </div>
        </div>
      )}
    </div>
  );
}
