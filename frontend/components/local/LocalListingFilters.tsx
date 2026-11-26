'use client';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useId, useState } from 'react';
import { localApi } from '@/api/local';
import { CityOption, LocalConfig, Region } from '@/lib/types';
import CityAutocomplete from './CityAutocomplete';
import ErrorState from '@/components/ui/ErrorState';
import { countActiveFilters } from '@/lib/local-filters';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Card } from '@/components/shadcn/card';
import { ICON_STROKE } from '@/lib/utils';
import { FIELD_CLASS, FIELD_LABEL_CLASS } from './field-classes';

export default function LocalListingFilters() {
  const router = useRouter();
  const sp = useSearchParams();
  const baseId = useId();
  const fid = (k: string) => `${baseId}-${k}`;
  // 10.24: на вузькому екрані фільтри згорнуті; на ≥768px блок завжди видно (md:block).
  const [open, setOpen] = useState(false);
  const activeCount = countActiveFilters((k) => sp.get(k));
  const panelId = `${baseId}-panel`;

  const [regions, setRegions] = useState<Region[]>([]);
  const [regionsError, setRegionsError] = useState<unknown>(null);
  const [config, setConfig] = useState<LocalConfig | null>(null);
  // 8.2: місто — пошуком у межах області; у URL лишається id.
  const [cityOption, setCityOption] = useState<CityOption | null>(null);

  const [make, setMake] = useState(sp.get('make') ?? '');
  const [model, setModel] = useState(sp.get('model') ?? '');
  const [yearMin, setYearMin] = useState(sp.get('year_min') ?? '');
  const [yearMax, setYearMax] = useState(sp.get('year_max') ?? '');
  const [priceMin, setPriceMin] = useState(sp.get('price_min') ?? '');
  const [priceMax, setPriceMax] = useState(sp.get('price_max') ?? '');
  const [fuel, setFuel] = useState(sp.get('fuel_type') ?? '');
  const [transmission, setTransmission] = useState(sp.get('transmission') ?? '');
  const [bodyType, setBodyType] = useState(sp.get('body_type') ?? '');
  const [region, setRegion] = useState(sp.get('region') ?? '');
  const [city, setCity] = useState(sp.get('city') ?? '');
  const [mileageMax, setMileageMax] = useState(sp.get('mileage_max') ?? '');
  const [search, setSearch] = useState(sp.get('search') ?? '');
  const [ordering, setOrdering] = useState(sp.get('ordering') ?? '-created_at');

  const loadRegions = useCallback(() => {
    setRegionsError(null);
    localApi.regions().then(setRegions).catch(setRegionsError);
  }, []);

  useEffect(() => {
    loadRegions();
  }, [loadRegions]);

  useEffect(() => {
    localApi.config().then(setConfig).catch(() => setConfig(null));
  }, []);

  // Посилання з ?city=<id>: підпис беремо зі швидкого списку області (великі міста), інакше — нейтральний.
  const initialCity = sp.get('city');
  const initialRegion = sp.get('region');
  useEffect(() => {
    if (!initialCity || !initialRegion) return;
    let alive = true;
    void localApi.cities(Number(initialRegion))
      .then((rows) => rows.find((c) => String(c.id) === initialCity))
      .catch(() => undefined)
      .then((c) => {
        if (!alive) return;
        setCityOption({
          id: Number(initialCity), name: c?.name ?? 'Обраний населений пункт', region: Number(initialRegion),
          region_name: c?.region_name ?? '', district_name: c?.district_name ?? '',
          label: c ? [c.name, c.region_name].filter(Boolean).join(' · ') : 'Обраний населений пункт',
        });
      });
    return () => { alive = false; };
  }, [initialCity, initialRegion]);

  function apply() {
    const p = new URLSearchParams();
    if (make) p.set('make', make);
    if (model) p.set('model', model);
    if (yearMin) p.set('year_min', yearMin);
    if (yearMax) p.set('year_max', yearMax);
    if (priceMin) p.set('price_min', priceMin);
    if (priceMax) p.set('price_max', priceMax);
    if (fuel) p.set('fuel_type', fuel);
    if (transmission) p.set('transmission', transmission);
    if (bodyType) p.set('body_type', bodyType);
    if (region) p.set('region', region);
    if (city) p.set('city', city);
    if (mileageMax) p.set('mileage_max', mileageMax);
    if (search) p.set('search', search);
    if (ordering) p.set('ordering', ordering);
    setOpen(false);
    router.push(`/ua?${p.toString()}`);
  }

  function reset() {
    setMake(''); setModel(''); setYearMin(''); setYearMax('');
    setPriceMin(''); setPriceMax(''); setFuel(''); setTransmission('');
    setBodyType(''); setRegion(''); setCity(''); setMileageMax('');
    setSearch(''); setOrdering('-created_at');
    setOpen(false);
    router.push('/ua');
  }

  const inputCls = FIELD_CLASS;
  const labelCls = FIELD_LABEL_CLASS;

  return (
    <Card className="gap-0 p-4">
      <button
        type="button"
        className="md:hidden w-full min-h-11 flex items-center justify-between gap-2 rounded-md text-sm font-semibold text-foreground"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="inline-flex items-center gap-2">
          <SlidersHorizontal className="size-5 text-link" strokeWidth={ICON_STROKE} aria-hidden="true" />
          <span>Фільтри{activeCount > 0 ? ` (${activeCount})` : ''}</span>
        </span>
        <ChevronDown className={`size-5 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} strokeWidth={ICON_STROKE} aria-hidden="true" />
      </button>
      <div id={panelId} className={`${open ? 'block' : 'hidden'} md:block space-y-4 mt-4 md:mt-0`}>
      {regionsError ? <ErrorState error={regionsError} onRetry={loadRegions} /> : null}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-4">
        <div className="col-span-2 md:col-span-1">
          <label htmlFor={fid('f1')} className={labelCls}>Пошук</label>
          <Input id={fid('f1')} placeholder="Марка, модель..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div>
          <label htmlFor={fid('f2')} className={labelCls}>Марка</label>
          <Input id={fid('f2')} placeholder="Toyota" value={make} onChange={e => setMake(e.target.value)} />
        </div>
        <div>
          <label htmlFor={fid('f3')} className={labelCls}>Модель</label>
          <Input id={fid('f3')} placeholder="Camry" value={model} onChange={e => setModel(e.target.value)} />
        </div>
        <div>
          <label htmlFor={fid('f4')} className={labelCls}>Тип палива</label>
          <select id={fid('f4')} className={inputCls} value={fuel} onChange={e => setFuel(e.target.value)}>
            <option value="">Всі</option>
            <option value="petrol">Бензин</option>
            <option value="diesel">Дизель</option>
            <option value="electric">Електро</option>
            <option value="hybrid">Гібрид</option>
            <option value="gas">Газ</option>
          </select>
        </div>
        <div>
          <label htmlFor={fid('f5')} className={labelCls}>Рік від</label>
          <Input id={fid('f5')} type="number" placeholder="2010" value={yearMin} onChange={e => setYearMin(e.target.value)} />
        </div>
        <div>
          <label htmlFor={fid('f6')} className={labelCls}>Рік до</label>
          <Input id={fid('f6')} type="number" placeholder="2024" value={yearMax} onChange={e => setYearMax(e.target.value)} />
        </div>
        <div>
          <label htmlFor={fid('f7')} className={labelCls}>Ціна від, $</label>
          <Input id={fid('f7')} type="number" placeholder="5000" value={priceMin} onChange={e => setPriceMin(e.target.value)} />
        </div>
        <div>
          <label htmlFor={fid('f8')} className={labelCls}>Ціна до, $</label>
          <Input id={fid('f8')} type="number" placeholder="30000" value={priceMax} onChange={e => setPriceMax(e.target.value)} />
        </div>
        <div>
          <label htmlFor={fid('f9')} className={labelCls}>КПП</label>
          <select id={fid('f9')} className={inputCls} value={transmission} onChange={e => setTransmission(e.target.value)}>
            <option value="">Всі</option>
            <option value="auto">Автомат</option>
            <option value="manual">Механіка</option>
            <option value="cvt">Варіатор</option>
            <option value="robot">Робот</option>
          </select>
        </div>
        <div>
          <label htmlFor={fid('f10')} className={labelCls}>Тип кузова</label>
          <select id={fid('f10')} className={inputCls} value={bodyType} onChange={e => setBodyType(e.target.value)}>
            <option value="">Всі</option>
            <option value="sedan">Седан</option>
            <option value="suv">Позашляховик</option>
            <option value="hatchback">Хетчбек</option>
            <option value="wagon">Універсал</option>
            <option value="coupe">Купе</option>
            <option value="minivan">Мінівен</option>
            <option value="pickup">Пікап</option>
          </select>
        </div>
        <div>
          <label htmlFor={fid('f11')} className={labelCls}>Область</label>
          <select id={fid('f11')} className={inputCls} value={region} onChange={e => { setRegion(e.target.value); setCity(''); setCityOption(null); }}>
            <option value="">Вся Україна</option>
            {regions.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
        <div>
          <CityAutocomplete
            id={fid('f12')}
            label="Населений пункт"
            labelClassName={labelCls}
            inputClassName={inputCls}
            placeholder="Усі населені пункти"
            value={cityOption}
            regionId={region ? Number(region) : undefined}
            minChars={config?.city_search_min_chars ?? 2}
            limit={config?.city_search_limit ?? 20}
            onChange={(opt) => {
              setCityOption(opt);
              setCity(opt ? String(opt.id) : '');
              if (opt) setRegion(String(opt.region));
            }}
          />
        </div>
        <div>
          <label htmlFor={fid('f13')} className={labelCls}>Пробіг до, км</label>
          <Input id={fid('f13')} type="number" placeholder="200000" value={mileageMax} onChange={e => setMileageMax(e.target.value)} />
        </div>
        <div>
          <label htmlFor={fid('f14')} className={labelCls}>Сортування</label>
          <select id={fid('f14')} className={inputCls} value={ordering} onChange={e => setOrdering(e.target.value)}>
            <option value="-created_at">Новіші спочатку</option>
            <option value="created_at">Старіші спочатку</option>
            <option value="price">Ціна ↑</option>
            <option value="-price">Ціна ↓</option>
          </select>
        </div>
      </div>
      <div className="flex flex-wrap gap-3 border-t pt-4">
        <Button type="button" onClick={apply} className="px-6 font-semibold">
          Застосувати
        </Button>
        <Button type="button" variant="outline" onClick={reset}>
          Скинути
        </Button>
      </div>
      </div>
    </Card>
  );
}
