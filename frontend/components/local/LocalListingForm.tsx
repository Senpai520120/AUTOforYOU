'use client';
import { trackEvent } from '@/lib/analytics';
import { useCallback, useId, useRef, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { localApi } from '@/api/local';
import EmailNotVerified from '@/components/ui/EmailNotVerified';
import { isEmailNotVerified } from '@/lib/email-verify';
import { Region, City, LocalListing, LocalListingImage } from '@/lib/types';
import ErrorState from '@/components/ui/ErrorState';
import LoadingState from '@/components/ui/LoadingState';
import PhotoUploadBlock from './PhotoUploadBlock';

/** Превью файлу: URL створюється один раз на файл і звільняється при видаленні/розмонтуванні. */
function FileThumb({ file, alt }: { file: File; alt: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const u = URL.createObjectURL(file);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  if (!url) return null;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={alt} width={160} height={160} className="object-cover w-full h-full" />;
}

function CreateModePhotoPicker({ onChange }: { onChange: (files: File[]) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? []);
    const next = [...files, ...selected].slice(0, 15);
    setFiles(next);
    onChange(next);
  }

  function remove(idx: number) {
    const next = files.filter((_, i) => i !== idx);
    setFiles(next);
    onChange(next);
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={files.length >= 15}
          className="text-sm bg-blue-50 hover:bg-blue-100 disabled:opacity-50 text-blue-700 border border-blue-200 rounded-lg px-3 py-1.5 transition-colors"
        >
          + Вибрати фото
        </button>
        <span className="text-xs text-slate-600">{files.length}/15 · jpg/png/webp · до 8 МБ</span>
        <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={handleChange} />
      </div>
      {files.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
          {files.map((f, i) => (
            <div key={i} className="relative group aspect-square rounded-lg overflow-hidden border border-slate-200 bg-slate-50">
              <FileThumb file={f} alt={`Фото ${i + 1} з ${files.length}`} />
              {i === 0 && (
                <span className="absolute top-1 left-1 bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded">Головне</span>
              )}
              <button
                type="button"
                onClick={() => remove(i)}
                className="absolute top-1 right-1 bg-white/90 hover:bg-white text-red-600 text-xs font-bold w-8 h-8 rounded-full flex items-center justify-center opacity-100 sm:opacity-0 sm:group-hover:opacity-100 focus:opacity-100 transition-opacity"
                aria-label="Видалити фото"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface Props {
  initial?: Partial<LocalListing>;
  listingId?: number;
}

export default function LocalListingForm({ initial, listingId }: Props) {
  const router = useRouter();
  const baseId = useId();
  const fid = (k: string) => `${baseId}-${k}`;
  const isEdit = !!listingId;

  const [regions, setRegions] = useState<Region[]>([]);
  const [regionsLoaded, setRegionsLoaded] = useState(false);
  const [regionsError, setRegionsError] = useState<unknown>(null);
  const [cities, setCities] = useState<City[]>([]);

  const [make, setMake] = useState(initial?.make ?? '');
  const [model, setModel] = useState(initial?.model ?? '');
  const [year, setYear] = useState(String(initial?.year ?? ''));
  const [mileageKm, setMileageKm] = useState(String(initial?.mileage_km ?? ''));
  const [engineCc, setEngineCc] = useState(String(initial?.engine_cc ?? ''));
  const [fuelType, setFuelType] = useState(initial?.fuel_type ?? 'petrol');
  const [transmission, setTransmission] = useState(initial?.transmission ?? 'auto');
  const [bodyType, setBodyType] = useState(initial?.body_type ?? 'sedan');
  const [condition, setCondition] = useState(initial?.condition ?? 'used');
  const [price, setPrice] = useState(String(initial?.price ?? ''));
  const [currency, setCurrency] = useState(initial?.currency ?? 'UAH');
  const [priceType, setPriceType] = useState(initial?.price_type ?? 'fixed');
  const [region, setRegion] = useState(String(initial?.region ?? ''));
  const [city, setCity] = useState(String(initial?.city ?? ''));
  const [description, setDescription] = useState(initial?.description ?? '');
  const [contactPhone, setContactPhone] = useState(initial?.contact_phone ?? '');
  const [agreedToRules, setAgreedToRules] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const [vin, setVin] = useState('');
  const [vinLoading, setVinLoading] = useState(false);
  const [vinError, setVinError] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notVerified, setNotVerified] = useState(false);

  // photo upload: in edit mode listingId is known upfront; in create mode we get it after creation
  const [createdListingId, setCreatedListingId] = useState<number | null>(listingId ?? null);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [photoError, setPhotoError] = useState('');

  const loadRegions = useCallback(() => {
    setRegionsError(null);
    setRegionsLoaded(false);
    localApi.regions().then(setRegions).catch(setRegionsError).finally(() => setRegionsLoaded(true));
  }, []);

  useEffect(() => {
    loadRegions();
  }, [loadRegions]);

  useEffect(() => {
    if (region) {
      localApi.cities(Number(region)).then(setCities).catch(() => setCities([]));
    } else {
      setCities([]);
    }
  }, [region]);

  async function handleVinPrefill() {
    if (vin.length !== 17) { setVinError('VIN має бути 17 символів'); return; }
    setVinLoading(true);
    setVinError('');
    try {
      const data = await localApi.vinPrefill(vin);
      if (data.error) { setVinError(`Помилка VIN: ${data.error}`); return; }
      if (data.make) setMake(data.make);
      if (data.model) setModel(data.model);
      if (data.year) setYear(String(data.year));
      if (data.engine_cc) setEngineCc(String(data.engine_cc));
      if (data.fuel_type) setFuelType(data.fuel_type as typeof fuelType);
    } catch {
      setVinError('Не вдалося отримати дані VIN. Спробуйте ще.');
    } finally {
      setVinLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErrors({});
    setNotVerified(false);
    const payload = {
      make, model, year: Number(year), mileage_km: Number(mileageKm),
      engine_cc: engineCc ? Number(engineCc) : null,
      fuel_type: fuelType, transmission, body_type: bodyType, condition,
      price, currency, price_type: priceType,
      region: Number(region), city: Number(city),
      description, contact_phone: contactPhone,
      ...(!isEdit ? { agreed_to_rules: agreedToRules } : {}),
    };
    try {
      if (isEdit) {
        await localApi.update(listingId, payload);
        router.push(`/local/${listingId}`);
      } else {
        const created = await localApi.create(payload);
        setCreatedListingId(created.id);
        trackEvent('listing_submit', { source: 'listing' });
        if (pendingFiles.length > 0) {
          try {
            await localApi.uploadImages(created.id, pendingFiles);
          } catch {
            setPhotoError('Оголошення створено, але фото не завантажились. Додайте їх у «Мої оголошення».');
          }
        }
        setSubmitted(true);
        return;
      }
    } catch (err: unknown) {
      if (isEmailNotVerified(err)) {
        setNotVerified(true);
        return;
      }
      const apiError = err as { data?: Record<string, string[]> };
      if (apiError?.data) {
        const mapped: Record<string, string> = {};
        for (const [k, v] of Object.entries(apiError.data)) {
          mapped[k] = Array.isArray(v) ? v.join(' ') : String(v);
        }
        setErrors(mapped);
      } else {
        setErrors({ _general: 'Сталася помилка. Перевірте поля та спробуйте знову.' });
      }
    } finally {
      setSubmitting(false);
    }
  }

  const inputCls = 'w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500';
  const labelCls = 'block text-sm font-medium text-slate-700 mb-1';
  const errCls = 'text-xs text-red-600 mt-1';

  if (submitted) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-8 text-center max-w-md mx-auto">
        <p className="text-4xl mb-4">🕐</p>
        <h2 className="text-xl font-bold text-blue-900 mb-2">Оголошення надіслано на модерацію</h2>
        <p className="text-sm text-blue-700 mb-4">
          Ми перевіримо оголошення і опублікуємо його незабаром. Ви отримаєте сповіщення.
        </p>
        <a href="/me/local-listings" className="text-blue-700 underline text-sm">
          Переглянути мої оголошення →
        </a>
      </div>
    );
  }

  // Без списку областей форма не відправиться: показуємо помилку з повтором, а не порожній select.
  if (regionsError) return <ErrorState error={regionsError} onRetry={loadRegions} />;
  if (!regionsLoaded) return <LoadingState />;

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
      {/* VIN prefill */}
      {!isEdit && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-sm font-medium text-amber-800 mb-2">Автозаповнення за VIN (безкоштовно)</p>
          <div className="flex gap-2">
            <input
              className={inputCls + ' flex-1 font-mono uppercase'}
              aria-label="VIN"
              placeholder="Введіть 17-значний VIN"
              value={vin}
              onChange={e => setVin(e.target.value.toUpperCase())}
              maxLength={17}
            />
            <button
              type="button"
              onClick={handleVinPrefill}
              disabled={vinLoading}
              className="bg-amber-500 hover:bg-amber-400 disabled:opacity-60 text-black font-semibold px-4 py-2 rounded-lg text-sm transition-colors"
            >
              {vinLoading ? 'Завантаження...' : 'Заповнити за VIN'}
            </button>
          </div>
          {vinError && <p role="alert" className={errCls}>{vinError}</p>}
        </div>
      )}

      {notVerified && <EmailNotVerified />}

      {errors._general && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700" role="alert">
          {errors._general}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor={fid('make')} className={labelCls}>Марка *</label>
          <input id={fid('make')} aria-invalid={!!errors.make} aria-describedby={errors.make ? fid('err-make') : undefined} className={inputCls} value={make} onChange={e => setMake(e.target.value)} required placeholder="Toyota" />
          {errors.make && <p id={fid('err-make')} role="alert" className={errCls}>{errors.make}</p>}
        </div>
        <div>
          <label htmlFor={fid('model')} className={labelCls}>Модель *</label>
          <input id={fid('model')} aria-invalid={!!errors.model} aria-describedby={errors.model ? fid('err-model') : undefined} className={inputCls} value={model} onChange={e => setModel(e.target.value)} required placeholder="Camry" />
          {errors.model && <p id={fid('err-model')} role="alert" className={errCls}>{errors.model}</p>}
        </div>
        <div>
          <label htmlFor={fid('year')} className={labelCls}>Рік *</label>
          <input id={fid('year')} aria-invalid={!!errors.year} aria-describedby={errors.year ? fid('err-year') : undefined} className={inputCls} type="number" value={year} onChange={e => setYear(e.target.value)} required placeholder="2020" min={1900} max={2026} />
          {errors.year && <p id={fid('err-year')} role="alert" className={errCls}>{errors.year}</p>}
        </div>
        <div>
          <label htmlFor={fid('mileage_km')} className={labelCls}>Пробіг, км *</label>
          <input id={fid('mileage_km')} aria-invalid={!!errors.mileage_km} aria-describedby={errors.mileage_km ? fid('err-mileage_km') : undefined} className={inputCls} type="number" value={mileageKm} onChange={e => setMileageKm(e.target.value)} required placeholder="50000" min={0} />
          {errors.mileage_km && <p id={fid('err-mileage_km')} role="alert" className={errCls}>{errors.mileage_km}</p>}
        </div>
        <div>
          <label htmlFor={fid('engine_cc')} className={labelCls}>Об&apos;єм двигуна, куб.см</label>
          <input id={fid('engine_cc')} className={inputCls} type="number" value={engineCc} onChange={e => setEngineCc(e.target.value)} placeholder="2000" min={0} />
        </div>
        <div>
          <label htmlFor={fid('fuel_type')} className={labelCls}>Тип палива *</label>
          <select id={fid('fuel_type')} className={inputCls} value={fuelType} onChange={e => setFuelType(e.target.value as typeof fuelType)} required>
            <option value="petrol">Бензин</option>
            <option value="diesel">Дизель</option>
            <option value="electric">Електро</option>
            <option value="hybrid">Гібрид</option>
            <option value="gas">Газ</option>
          </select>
        </div>
        <div>
          <label htmlFor={fid('transmission')} className={labelCls}>КПП *</label>
          <select id={fid('transmission')} className={inputCls} value={transmission} onChange={e => setTransmission(e.target.value as typeof transmission)} required>
            <option value="auto">Автомат</option>
            <option value="manual">Механіка</option>
            <option value="cvt">Варіатор</option>
            <option value="robot">Робот</option>
          </select>
        </div>
        <div>
          <label htmlFor={fid('body_type')} className={labelCls}>Тип кузова *</label>
          <select id={fid('body_type')} className={inputCls} value={bodyType} onChange={e => setBodyType(e.target.value as typeof bodyType)} required>
            <option value="sedan">Седан</option>
            <option value="suv">Позашляховик</option>
            <option value="hatchback">Хетчбек</option>
            <option value="wagon">Універсал</option>
            <option value="coupe">Купе</option>
            <option value="minivan">Мінівен</option>
            <option value="pickup">Пікап</option>
            <option value="convertible">Кабріолет</option>
            <option value="other">Інше</option>
          </select>
        </div>
        <div>
          <label htmlFor={fid('condition')} className={labelCls}>Стан *</label>
          <select id={fid('condition')} className={inputCls} value={condition} onChange={e => setCondition(e.target.value as typeof condition)} required>
            <option value="used">Вживаний</option>
            <option value="new">Новий</option>
            <option value="damaged">Пошкоджений</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="sm:col-span-2">
          <label htmlFor={fid('price')} className={labelCls}>Ціна *</label>
          <input id={fid('price')} aria-invalid={!!errors.price} aria-describedby={errors.price ? fid('err-price') : undefined} className={inputCls} type="number" value={price} onChange={e => setPrice(e.target.value)} required placeholder="500000" min={0} />
          {errors.price && <p id={fid('err-price')} role="alert" className={errCls}>{errors.price}</p>}
        </div>
        <div>
          <label htmlFor={fid('currency')} className={labelCls}>Валюта</label>
          <select id={fid('currency')} className={inputCls} value={currency} onChange={e => setCurrency(e.target.value as typeof currency)}>
            <option value="UAH">UAH</option>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
          </select>
        </div>
        <div className="sm:col-span-3">
          <span id={fid('price_type')} className={labelCls}>Тип ціни</span>
          <div role="radiogroup" aria-labelledby={fid('price_type')} className="flex gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="radio" value="fixed" checked={priceType === 'fixed'} onChange={() => setPriceType('fixed')} /> Фіксована
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="radio" value="negotiable" checked={priceType === 'negotiable'} onChange={() => setPriceType('negotiable')} /> Торг
            </label>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor={fid('region')} className={labelCls}>Область *</label>
          <select id={fid('region')} aria-invalid={!!errors.region} aria-describedby={errors.region ? fid('err-region') : undefined} className={inputCls} value={region} onChange={e => { setRegion(e.target.value); setCity(''); }} required>
            <option value="">Оберіть область</option>
            {regions.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          {errors.region && <p id={fid('err-region')} role="alert" className={errCls}>{errors.region}</p>}
        </div>
        <div>
          <label htmlFor={fid('city')} className={labelCls}>Місто *</label>
          <select id={fid('city')} aria-invalid={!!errors.city} aria-describedby={errors.city ? fid('err-city') : undefined} className={inputCls} value={city} onChange={e => setCity(e.target.value)} required disabled={!region}>
            <option value="">Оберіть місто</option>
            {cities.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {errors.city && <p id={fid('err-city')} role="alert" className={errCls}>{errors.city}</p>}
        </div>
      </div>

      {/* Photo block — edit mode: immediate upload; create mode: buffer until submit */}
      <div>
        <span className={labelCls}>Фото</span>
        {isEdit && createdListingId ? (
          <PhotoUploadBlock
            listingId={createdListingId}
            initial={(initial as LocalListing | undefined)?.images ?? []}
          />
        ) : (
          <CreateModePhotoPicker onChange={setPendingFiles} />
        )}
        {photoError && <p role="alert" className="text-xs text-red-600 mt-1">{photoError}</p>}
      </div>

      <div>
        <label htmlFor={fid('description')} className={labelCls}>Опис</label>
        <textarea id={fid('description')}
          className={inputCls}
          rows={5}
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Розкажіть детальніше про автомобіль..."
        />
      </div>

      <div>
        <label htmlFor={fid('contact_phone')} className={labelCls}>Контактний телефон</label>
        <input id={fid('contact_phone')}
          className={inputCls}
          type="tel"
          value={contactPhone}
          onChange={e => setContactPhone(e.target.value)}
          placeholder="+38 050 123 45 67"
        />
        <p className="text-xs text-slate-600 mt-1">Показується тільки авторизованим покупцям</p>
      </div>

      {!isEdit && (
        <div>
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600"
              checked={agreedToRules}
              onChange={e => setAgreedToRules(e.target.checked)}
              required
            />
            <span className="text-sm text-slate-700">
              Погоджуюсь з{' '}
              <a href="/rules" target="_blank" className="text-blue-600 underline">
                правилами розміщення оголошень
              </a>{' '}
              та{' '}
              <a href="/terms" target="_blank" className="text-blue-600 underline">
                умовами використання
              </a>
            </span>
          </label>
          {errors.agreed_to_rules && <p id={fid('err-agreed_to_rules')} role="alert" className={errCls}>{errors.agreed_to_rules}</p>}
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <button
          type="submit"
          disabled={submitting}
          className="bg-blue-700 hover:bg-blue-600 disabled:opacity-60 text-white font-semibold px-8 py-3 rounded-lg transition-colors"
        >
          {submitting ? 'Збереження...' : isEdit ? 'Зберегти зміни' : 'Опублікувати оголошення'}
        </button>
        <button
          type="button"
          onClick={() => router.back()}
          className="border border-slate-300 hover:bg-slate-50 text-slate-600 px-6 py-3 rounded-lg transition-colors"
        >
          Скасувати
        </button>
      </div>
    </form>
  );
}
