'use client';
import Image from 'next/image';
import { isLocalMediaUrl } from '@/lib/media';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { LocalListing } from '@/lib/types';
import { useAuth } from '@/lib/auth-context';
import { localApi } from '@/api/local';
import WriteSellerButton from '@/components/messaging/WriteSellerButton';
import HeartButton from '@/components/favorites/HeartButton';
import ReportButton from '@/components/reports/ReportButton';
import ChannelBadge from '@/components/local/ChannelBadge';
import GuestPhoneReveal from '@/components/local/GuestPhoneReveal';
import MobileActionBar, { countBarClick, mobileBarButtonClass } from '@/components/ui/MobileActionBar';
import { CATALOG_LABEL, MOBILE_BAR_LABELS, VERIFIED_DEALER_LABEL } from '@/lib/labels';
import SellerBlock from '@/components/trust/SellerBlock';
import ScamWarningBanner from '@/components/trust/ScamWarningBanner';
import { PHONE_BLOCK_ID, usePhoneReveal } from '@/lib/usePhoneReveal';
import { useC2C } from '@/components/c2c/C2CProvider';
import ListingCheckTips from '@/components/local/ListingCheckTips';
import {
  CalendarDays, CarFront, ChevronRight, Cog, Fuel, Gauge, MapPin, Pencil, Phone, Settings2, ShieldCheck, Star,
} from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Card } from '@/components/shadcn/card';
import { ICON_STROKE } from '@/lib/utils';

const WRITE_BLOCK_ID = 'write-seller-block';

const PLACEHOLDER_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='800' height='600' viewBox='0 0 800 600'%3E%3Crect width='800' height='600' fill='%23e2e8f0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='18' fill='%23475569'%3EФото відсутнє%3C/text%3E%3C/svg%3E";

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
  // У «засіві» переписка, обране й скарги по C2C закриті (бекенд відповідає 404), кнопки ховаємо.
  const social = useC2C().social;
  const [activeImg, setActiveImg] = useState(0);
  // 4.5a/6.6: один стан показу телефону для блоку на сторінці і нижньої панелі.
  const phoneReveal = usePhoneReveal(listing.id, !user);
  const { phone, loading: phoneLoading, error: phoneError } = phoneReveal;

  const images = listing.images.length > 0 ? listing.images : [{ id: 0, image: null, source_url: '', is_primary: true }];
  const activeSrc = images[activeImg]?.image || images[activeImg]?.source_url || PLACEHOLDER_SVG;
  // 10.3: адреси фото, що не завантажились; заглушка через state, без циклу запитів.
  const [failedSrcs, setFailedSrcs] = useState<ReadonlySet<string>>(() => new Set());
  const markFailed = (src: string) =>
    setFailedSrcs((prev) => (prev.has(src) ? prev : new Set(prev).add(src)));
  const mainImg = failedSrcs.has(activeSrc) ? PLACEHOLDER_SVG : activeSrc;
  // SSR-HTML публичный и кэшируется (is_owner там всегда false), поэтому признак владельца
  // берём из авторизованного запроса на клиенте.
  const [ownerFlag, setOwnerFlag] = useState(false);
  // 6.6: поки ознака власника не відома, панель не показуємо (власник не має витратити ліміт на свій номер).
  const [ownerResolved, setOwnerResolved] = useState(false);
  const isOwner = Boolean(user) && ownerFlag;
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    localApi.detail(listing.id)
      .then(d => { if (!cancelled) setOwnerFlag(Boolean(d.is_owner)); })
      .catch(() => { if (!cancelled) setOwnerFlag(false); })
      .finally(() => { if (!cancelled) setOwnerResolved(true); });
    return () => { cancelled = true; };
  }, [user, listing.id]);

  const price = Number(listing.price).toLocaleString('uk-UA');

  const specs = [
    { label: 'Рік', value: listing.year, Icon: CalendarDays },
    { label: 'Пробіг', value: `${listing.mileage_km.toLocaleString()} км`, Icon: Gauge },
    { label: 'Паливо', value: FUEL_LABELS[listing.fuel_type] ?? listing.fuel_type, Icon: Fuel },
    { label: 'КПП', value: TRANSMISSION_LABELS[listing.transmission] ?? listing.transmission, Icon: Settings2 },
    { label: 'Кузов', value: BODY_LABELS[listing.body_type] ?? listing.body_type, Icon: CarFront },
    { label: 'Стан', value: CONDITION_LABELS[listing.condition] ?? listing.condition, Icon: ShieldCheck },
    listing.engine_cc ? { label: "Об'єм двигуна", value: `${(listing.engine_cc / 1000).toFixed(1)} л (${listing.engine_cc} куб.см)`, Icon: Cog } : null,
  ].filter(Boolean) as { label: string; value: string | number; Icon: typeof Gauge }[];


  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-4 flex items-center gap-1 text-sm text-muted-foreground">
        <Link href="/ua" className="inline-flex min-h-11 items-center underline-offset-4 hover:text-link hover:underline">{CATALOG_LABEL}</Link>
        <ChevronRight className="size-4" strokeWidth={ICON_STROKE} aria-hidden="true" />
        <span>{listing.make} {listing.model}</span>
      </div>

      {social && (
        <div className="flex justify-end mb-2">
          <HeartButton listingType="local" listingId={listing.id} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Gallery */}
        <div>
          <div className="relative aspect-[4/3] overflow-hidden rounded-xl border bg-muted">
            <Image
              src={mainImg}
              alt={`${listing.make} ${listing.model} ${listing.year}`}
              fill
              className="object-cover"
              sizes="(max-width: 1024px) 100vw, 50vw"
              priority
              unoptimized={isLocalMediaUrl(mainImg)}
              onError={() => markFailed(activeSrc)}
            />
          </div>
          {images.length > 1 && (
            <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
              {images.map((img, i) => {
                const thumbSrc = img.image || img.source_url || PLACEHOLDER_SVG;
                return (
                <button
                  key={img.id || i}
                  onClick={() => setActiveImg(i)}
                  aria-current={i === activeImg ? 'true' : undefined}
                  className={`relative size-16 flex-shrink-0 overflow-hidden rounded-md border-2 transition-colors ${i === activeImg ? 'border-primary' : 'border-transparent hover:border-input'}`}
                >
                  <Image
                    src={failedSrcs.has(thumbSrc) ? PLACEHOLDER_SVG : thumbSrc}
                    alt={`Фото ${i + 1} з ${images.length} — ${listing.make} ${listing.model} ${listing.year}`}
                    fill
                    className="object-cover"
                    sizes="64px"
                    unoptimized={isLocalMediaUrl(thumbSrc)}
                    onError={() => markFailed(thumbSrc)}
                  />
                </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Info panel */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground md:text-3xl">
            {listing.make} {listing.model} {listing.year}
          </h1>
          <p className="mt-2 inline-flex items-center gap-1 text-sm text-muted-foreground">
            <MapPin className="size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
            {listing.city_name}, {listing.region_name}
          </p>

          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-4xl font-extrabold tracking-tight text-foreground">
              {price} {listing.currency}
            </span>
            {listing.price_type === 'negotiable' && (
              <span className="text-muted-foreground text-sm">— торг</span>
            )}
          </div>

          <Card className="mt-6 gap-0 p-4">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              {specs.map(s => (
                <div key={s.label} className="flex items-center justify-between gap-3 border-b border-border pb-2 sm:flex-col sm:items-start sm:justify-start sm:gap-0.5">
                  <dt className="inline-flex items-center gap-1.5 text-muted-foreground">
                    <s.Icon className="size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
                    {s.label}
                  </dt>
                  <dd className="font-semibold text-foreground">{s.value}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card className="mt-4 gap-0 border-primary/30 bg-primary/5 p-4">
            <div className="text-sm text-muted-foreground flex flex-wrap items-center gap-1.5">
              <span>Продавець: <strong className="text-foreground">{listing.owner_name}</strong></span>
              {listing.seller_type === 'dealer' && (
                <span data-testid="verified-dealer" className="rounded-full bg-link/10 px-2 py-0.5 text-xs font-semibold text-link">✓ {VERIFIED_DEALER_LABEL}</span>
              )}
              {listing.seller_has_badge && (
                <span className="rounded-full bg-success px-2 py-0.5 text-xs font-semibold text-success-foreground">
                  ✓ Перевірений продавець
                </span>
              )}
              <ChannelBadge channel={listing.source_channel} />
            </div>
            {listing.seller_has_badge && listing.seller_avg_rating && (
              <div className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
                <Star className="size-4 fill-warning text-warning-foreground" strokeWidth={ICON_STROKE} aria-hidden="true" />
                <span>{listing.seller_avg_rating.toFixed(1)}</span>
                {listing.seller_deal_count ? <span>· {listing.seller_deal_count} угод</span> : null}
              </div>
            )}
            <SellerBlock listing={listing} />
            {!isOwner && <ScamWarningBanner className="mt-3" />}
            <div className="mt-3" id={PHONE_BLOCK_ID}>
              {phone ? (
                <Button asChild size="lg" className="w-full bg-success text-success-foreground text-base font-semibold hover:bg-success/90">
                  <a href={`tel:${phone}`}>
                    <Phone strokeWidth={ICON_STROKE} aria-hidden="true" />
                    {phone}
                  </a>
                </Button>
              ) : !user ? (
                <GuestPhoneReveal
                  listingId={listing.id}
                  open={phoneReveal.guestOpen}
                  onOpen={() => phoneReveal.setGuestOpen(true)}
                  onPhone={phoneReveal.onGuestPhone}
                />
              ) : (
                <Button type="button" size="lg" onClick={phoneReveal.reveal} disabled={phoneLoading} className="w-full font-semibold">
                  <Phone strokeWidth={ICON_STROKE} aria-hidden="true" />
                  {phoneLoading ? 'Завантаження...' : 'Показати телефон'}
                </Button>
              )}
              {phoneError && <p role="alert" className="mt-1 text-xs text-destructive">{phoneError}</p>}
            </div>
          </Card>

          {social && !isOwner && listing.status === 'active' && (
            <div className="mt-3" id={WRITE_BLOCK_ID}>
              <WriteSellerButton listingType="local" listingId={listing.id} />
            </div>
          )}

          {social && isOwner && (
            <div className="mt-3 flex gap-2">
              <Button asChild variant="outline" className="flex-1 border-primary font-semibold text-primary hover:bg-primary/5 hover:text-primary">
                <Link href={`/local/${listing.id}/edit`}>
                  <Pencil strokeWidth={ICON_STROKE} aria-hidden="true" />
                  Редагувати
                </Link>
              </Button>
            </div>
          )}

          {social && !isOwner && (
            <div className="mt-3 flex justify-end">
              <ReportButton listingId={listing.id} />
            </div>
          )}
        </div>
      </div>

      {listing.description && (
        <div className="mt-8">
          <h2 className="mb-3 text-lg font-bold text-foreground">Опис</h2>
          <Card className="gap-0 p-4 text-sm text-foreground whitespace-pre-line">
            {listing.description}
          </Card>
        </div>
      )}

      <ListingCheckTips />

      {listing.status === 'active' && !isOwner && (!user || ownerResolved) && (
        <MobileActionBar
          actions={[
            {
              key: 'call',
              node: phone ? (
                <a href={`tel:${phone}`} onClick={countBarClick}
                  className={`${mobileBarButtonClass} bg-success text-success-foreground hover:bg-success/90`}>
                  {MOBILE_BAR_LABELS.call}
                </a>
              ) : (
                <button
                  type="button"
                  onClick={() => { countBarClick(); void phoneReveal.reveal(); }}
                  disabled={phoneLoading}
                  className={`${mobileBarButtonClass} bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-60`}
                >
                  {phoneLoading ? 'Завантаження...' : MOBILE_BAR_LABELS.call}
                </button>
              ),
            },
            ...(social
              ? [{
                key: 'write',
                // Той самий діалог, що й кнопка на сторінці: другого екземпляра модалки немає.
                node: (
                  <button
                    type="button"
                    onClick={() => {
                      countBarClick();
                      document.querySelector<HTMLButtonElement>(`#${WRITE_BLOCK_ID} button`)?.click();
                    }}
                    className={`${mobileBarButtonClass} border border-primary bg-card text-primary hover:bg-primary/5`}
                  >
                    {MOBILE_BAR_LABELS.write}
                  </button>
                ),
              }]
              : []),
          ]}
        />
      )}
    </div>
  );
}
