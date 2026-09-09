import type { Metadata } from 'next';
import Link from 'next/link';
import ListingCard from '@/components/listings/ListingCard';
import type { Listing, PaginatedResponse } from '@/lib/types';

// INTERNAL_API_URL задається в Docker (http://backend:8000) для SSR.
const apiUrl = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/**
 * Рендер на кожен запит, а не на етапі збірки.
 *
 * Без цього Next пререндерив головну під час `npm run build` всередині
 * білд-контейнера, де backend:8000 недоступний. Обидва запити падали в
 * catch, і в HTML запікалися порожні фолбэки: ні свіжих лотів, ні курсу.
 * Дані самі кешуються на рівні fetch, тож зайвого навантаження немає.
 */
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'AUTOforYOU — авто з США під ключ',
  description:
    'Маркетплейс автомобілів з аукціонів США Copart та IAAI. Калькулятор вартості під ключ з розмитненням, доставка в Україну, каталог місцевих оголошень.',
  openGraph: {
    title: 'AUTOforYOU — авто з США під ключ',
    description: 'Авто з аукціонів Copart та IAAI, калькулятор розмитнення, каталог оголошень по Україні.',
    type: 'website',
  },
};

type ExchangeRate = { from_currency: string; to_currency: string; rate: number; date: string };

/** Свіжі роздрібні лоти. Порожній масив — блок просто не рендериться. */
async function fetchLatestListings(): Promise<Listing[]> {
  try {
    const res = await fetch(`${apiUrl}/api/v1/listings/?channel=retail`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return [];
    const data: PaginatedResponse<Listing> = await res.json();
    return data.results.slice(0, 3);
  } catch {
    return [];
  }
}

/** Актуальний курс НБУ. null — блок покаже формулу без конкретної цифри. */
async function fetchUsdRate(): Promise<ExchangeRate | null> {
  try {
    const res = await fetch(`${apiUrl}/api/v1/pricing/rates/`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    const data: { exchange_rates?: ExchangeRate[] } = await res.json();
    return data.exchange_rates?.find(r => r.from_currency === 'USD' && r.to_currency === 'UAH') ?? null;
  } catch {
    return null;
  }
}

const STEPS = [
  {
    n: '1',
    title: 'Обираєте лот',
    text: 'Знаходите авто на Copart або IAAI чи в нашому каталозі. Перевіряєте VIN і стан.',
  },
  {
    n: '2',
    title: 'Рахуєте вартість',
    text: 'Калькулятор показує повну суму «під ключ»: аукціонний збір, логістика, розмитнення.',
  },
  {
    n: '3',
    title: 'Викуп і доставка',
    text: 'Авто їде на склад у США, далі морем до порту ЄС і автовозом в Україну.',
  },
  {
    n: '4',
    title: 'Розмитнення',
    text: 'Акциз, мито, ПДВ і пенсійний збір. Контейнер відстежується в особистому кабінеті.',
  },
];

const COST_ITEMS = [
  'Ставка на аукціоні',
  'Аукціонний збір: buyer fee, gate, environmental, virtual bid',
  'Доставка до порту США',
  'Морський фрахт до Клайпеди або Гданська',
  'Доставка ЄС → Україна',
  'Акциз: 50–150 €/л залежно від палива й об’єму',
  'Мито 10% від митної вартості',
  'ПДВ 20%',
  'Пенсійний збір',
];

export default async function Home() {
  const [listings, usdRate] = await Promise.all([fetchLatestListings(), fetchUsdRate()]);

  return (
    <div className="space-y-14">
      {/* Hero */}
      <section className="bg-gradient-to-br from-blue-900 to-blue-700 text-white rounded-2xl p-12 text-center">
        <h1 className="text-4xl font-extrabold mb-3">Авто з США під ключ в Україну</h1>
        <p className="text-blue-200 text-lg mb-8 max-w-xl mx-auto">
          Copart · IAAI · доставка · розмитнення · калькулятор вартості
        </p>
        <div className="flex flex-wrap gap-4 justify-center">
          <Link
            href="/calculator"
            className="bg-amber-400 hover:bg-amber-300 text-black font-bold px-8 py-3 rounded-xl text-lg transition-colors focus:outline-none focus:ring-2 focus:ring-amber-200"
          >
            Порахувати вартість
          </Link>
          <Link
            href="/listings"
            className="bg-white/10 hover:bg-white/20 border border-white/30 text-white font-semibold px-8 py-3 rounded-xl text-lg transition-colors focus:outline-none focus:ring-2 focus:ring-white/50"
          >
            Переглянути каталог
          </Link>
        </div>
        <p className="mt-6 text-xs text-amber-300">
          ⚠ Тестові тарифи — всі розрахунки є демонстраційними
        </p>
      </section>

      {/* Два напрямки — прибирає плутанину між імпортом і локальним каталогом */}
      <section aria-labelledby="directions-heading">
        <h2 id="directions-heading" className="text-2xl font-bold text-slate-900 mb-6">
          Два напрямки
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Link
            href="/listings"
            className="bg-white border border-slate-200 rounded-xl p-6 hover:shadow-md hover:border-blue-300 transition-all group focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <div className="text-4xl mb-3" aria-hidden="true">🇺🇸</div>
            <h3 className="font-bold text-lg text-slate-900 group-hover:text-blue-700 transition-colors mb-1">
              Імпорт з аукціонів США
            </h3>
            <p className="text-sm text-slate-500">
              Лоти Copart та IAAI, розрахунок «під ключ», відстеження контейнера від складу до гаража.
            </p>
          </Link>
          <Link
            href="/ua"
            className="bg-white border border-slate-200 rounded-xl p-6 hover:shadow-md hover:border-blue-300 transition-all group focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <div className="text-4xl mb-3" aria-hidden="true">🇺🇦</div>
            <h3 className="font-bold text-lg text-slate-900 group-hover:text-blue-700 transition-colors mb-1">
              Каталог Україна
            </h3>
            <p className="text-sm text-slate-500">
              Оголошення від власників і дилерів по всій Україні. Подати своє — безкоштовно.
            </p>
          </Link>
        </div>
      </section>

      {/* Як це працює */}
      <section aria-labelledby="how-heading">
        <h2 id="how-heading" className="text-2xl font-bold text-slate-900 mb-6">
          Як це працює
        </h2>
        <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {STEPS.map(s => (
            <li key={s.n} className="bg-white border border-slate-200 rounded-xl p-5">
              <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-700 text-white font-bold text-sm mb-3">
                {s.n}
              </span>
              <h3 className="font-semibold text-slate-900 mb-1">{s.title}</h3>
              <p className="text-sm text-slate-500">{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Що входить у розрахунок */}
      <section aria-labelledby="cost-heading" className="bg-white border border-slate-200 rounded-xl p-6 md:p-8">
        <h2 id="cost-heading" className="text-2xl font-bold text-slate-900 mb-2">
          Що входить у розрахунок
        </h2>
        <p className="text-sm text-slate-500 mb-6">
          Калькулятор розкладає суму на статті — без прихованих рядків. Кожен розрахунок зберігає
          знімок застосованих ставок і курсу, тож до нього можна повернутися пізніше.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
          {COST_ITEMS.map(item => (
            <div key={item} className="flex items-start gap-2 text-sm text-slate-700">
              <span className="text-blue-700 mt-0.5" aria-hidden="true">•</span>
              <span>{item}</span>
            </div>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <Link
            href="/calculator"
            className="bg-blue-700 hover:bg-blue-800 text-white font-semibold px-6 py-2.5 rounded-xl transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            Відкрити калькулятор
          </Link>
          {usdRate && (
            <p className="text-sm text-slate-500">
              Курс НБУ на {usdRate.date}:{' '}
              <strong className="text-slate-800 font-mono">{usdRate.rate} грн/$</strong>
            </p>
          )}
        </div>
      </section>

      {/* Свіжі авто — рендериться тільки якщо є що показати */}
      {listings.length > 0 && (
        <section aria-labelledby="latest-heading">
          <div className="flex items-center justify-between mb-6">
            <h2 id="latest-heading" className="text-2xl font-bold text-slate-900">
              Свіжі авто
            </h2>
            <Link href="/listings" className="text-sm text-blue-700 hover:underline">
              Весь каталог →
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {listings.map(l => (
              <ListingCard key={l.id} listing={l} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
