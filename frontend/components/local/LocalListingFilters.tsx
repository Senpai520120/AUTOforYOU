'use client';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { localApi } from '@/api/local';
import { Region, City } from '@/lib/types';

export default function LocalListingFilters() {
  const router = useRouter();
  const sp = useSearchParams();

  const [regions, setRegions] = useState<Region[]>([]);
  const [cities, setCities] = useState<City[]>([]);

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

  useEffect(() => {
    localApi.regions().then(setRegions).catch(() => {});
  }, []);

  useEffect(() => {
    if (region) {
      localApi.cities(Number(region)).then(setCities).catch(() => setCities([]));
    } else {
      setCities([]);
      setCity('');
    }
  }, [region]);

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
    router.push(`/ua?${p.toString()}`);
  }

  function reset() {
    setMake(''); setModel(''); setYearMin(''); setYearMax('');
    setPriceMin(''); setPriceMax(''); setFuel(''); setTransmission('');
    setBodyType(''); setRegion(''); setCity(''); setMileageMax('');
    setSearch(''); setOrdering('-created_at');
    router.push('/ua');
  }

  const inputCls = 'w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500';
  const labelCls = 'block text-xs font-medium text-slate-600 mb-1';

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label className={labelCls}>Пошук</label>
          <input className={inputCls} placeholder="Марка, модель..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Марка</label>
          <input className={inputCls} placeholder="Toyota" value={make} onChange={e => setMake(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Модель</label>
          <input className={inputCls} placeholder="Camry" value={model} onChange={e => setModel(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Тип палива</label>
          <select className={inputCls} value={fuel} onChange={e => setFuel(e.target.value)}>
            <option value="">Всі</option>
            <option value="petrol">Бензин</option>
            <option value="diesel">Дизель</option>
            <option value="electric">Електро</option>
            <option value="hybrid">Гібрид</option>
            <option value="gas">Газ</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>Рік від</label>
          <input className={inputCls} type="number" placeholder="2010" value={yearMin} onChange={e => setYearMin(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Рік до</label>
          <input className={inputCls} type="number" placeholder="2024" value={yearMax} onChange={e => setYearMax(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Ціна від</label>
          <input className={inputCls} type="number" placeholder="100000" value={priceMin} onChange={e => setPriceMin(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Ціна до</label>
          <input className={inputCls} type="number" placeholder="1000000" value={priceMax} onChange={e => setPriceMax(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>КПП</label>
          <select className={inputCls} value={transmission} onChange={e => setTransmission(e.target.value)}>
            <option value="">Всі</option>
            <option value="auto">Автомат</option>
            <option value="manual">Механіка</option>
            <option value="cvt">Варіатор</option>
            <option value="robot">Робот</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>Тип кузова</label>
          <select className={inputCls} value={bodyType} onChange={e => setBodyType(e.target.value)}>
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
          <label className={labelCls}>Область</label>
          <select className={inputCls} value={region} onChange={e => { setRegion(e.target.value); setCity(''); }}>
            <option value="">Вся Україна</option>
            {regions.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Місто</label>
          <select className={inputCls} value={city} onChange={e => setCity(e.target.value)} disabled={!region}>
            <option value="">Всі міста</option>
            {cities.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Пробіг до, км</label>
          <input className={inputCls} type="number" placeholder="200000" value={mileageMax} onChange={e => setMileageMax(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Сортування</label>
          <select className={inputCls} value={ordering} onChange={e => setOrdering(e.target.value)}>
            <option value="-created_at">Новіші спочатку</option>
            <option value="created_at">Старіші спочатку</option>
            <option value="price">Ціна ↑</option>
            <option value="-price">Ціна ↓</option>
          </select>
        </div>
      </div>
      <div className="flex gap-3">
        <button
          onClick={apply}
          className="bg-blue-700 hover:bg-blue-600 text-white px-6 py-2 rounded-lg text-sm font-semibold transition-colors"
        >
          Застосувати
        </button>
        <button
          onClick={reset}
          className="border border-slate-300 hover:bg-slate-50 text-slate-600 px-4 py-2 rounded-lg text-sm transition-colors"
        >
          Скинути
        </button>
      </div>
    </div>
  );
}
