import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Calculator, Check, ClipboardCheck, MapPin, Search, Ship, type LucideIcon } from 'lucide-react';
import { CATALOG_LABEL } from '@/lib/labels';
import { getC2CFlags } from '@/lib/c2c';
import { getDemoStatus } from '@/lib/site-config';
import { getSiteSettings } from '@/lib/site-settings';
import { organizationLd, websiteLd } from '@/lib/jsonld';
import JsonLd from '@/components/seo/JsonLd';
import { buildMetadata } from '@/lib/seo';
import { serverGet } from '@/lib/server-api';
import { getLandingList, POPULAR_LANDINGS_LIMIT } from '@/lib/landings';
import PopularModels from '@/components/landing/PopularModels';
import { Button } from '@/components/shadcn/button';
import { Card, CardContent } from '@/components/shadcn/card';
import { ICON_STROKE } from '@/lib/utils';

/**
 * Рендер на кожен запит, а не на етапі збірки.
 *
 * Без цього Next пререндерив головну під час `npm run build` всередині
 * білд-контейнера, де backend:8000 недоступний. Обидва запити падали в
 * catch, і в HTML запікалися порожні фолбэки: ні свіжих лотів, ні курсу.
 * Дані самі кешуються на рівні fetch, тож зайвого навантаження немає.
 */
export const dynamic = 'force-dynamic';

export const metadata: Metadata = buildMetadata({
  title: 'AUTOforYOU — пригон авто з США під ключ',
  absoluteTitle: true,
  description:
    'Пригон авто з аукціонів США Copart та IAAI під ключ: калькулятор вартості з розмитненням, доставка в Україну, каталог місцевих оголошень.',
  path: '/',
  ownImage: true,
});

type ExchangeRate = { from_currency: string; to_currency: string; rate: number; date: string };

/** Актуальний курс НБУ через спільний serverGet (кеш 1 год). null — блок покаже формулу без цифри. */
async function fetchUsdRate(): Promise<ExchangeRate | null> {
  const data = await serverGet<{ exchange_rates?: ExchangeRate[] }>('/api/v1/pricing/rates/', 3600);
  return data?.exchange_rates?.find(r => r.from_currency === 'USD' && r.to_currency === 'UAH') ?? null;
}

const STEPS: { n: string; title: string; text: string; icon: LucideIcon }[] = [
  {
    n: '1',
    title: 'Обираєте лот',
    text: 'Знаходите авто на Copart або IAAI. Перевіряєте VIN і стан.',
    icon: Search,
  },
  {
    n: '2',
    title: 'Рахуєте вартість',
    text: 'Калькулятор показує повну суму «під ключ»: аукціонний збір, логістика, розмитнення.',
    icon: Calculator,
  },
  {
    n: '3',
    title: 'Викуп і доставка',
    text: 'Авто їде на склад у США, далі морем до порту ЄС і автовозом в Україну.',
    icon: Ship,
  },
  {
    n: '4',
    title: 'Розмитнення',
    text: 'Акциз, мито, ПДВ і пенсійний збір. Контейнер відстежується в особистому кабінеті.',
    icon: ClipboardCheck,
  },
];

const COST_ITEMS = [
  'Ставка на аукціоні',
  'Аукціонний збір і супутні збори аукціону',
  'Доставка до порту США',
  'Морський фрахт до порту ЄС',
  'Доставка ЄС → Україна',
  'Акциз — залежить від палива та об’єму двигуна',
  'Мито та ПДВ',
  'Пенсійний збір',
];

const H2 = 'text-2xl font-bold tracking-tight text-foreground mb-6';
const CARD_LINK = 'group block rounded-xl transition-transform motion-safe:hover:-translate-y-0.5';
const CARD_HOVER = 'h-full transition-shadow group-hover:border-primary group-hover:shadow-md';

/** Іконка в плитці: декоративна, назву несе заголовок поруч. */
function IconTile({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="inline-flex size-12 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden="true">
      <Icon className="size-6" strokeWidth={ICON_STROKE} />
    </span>
  );
}

export default async function Home() {
  const [usdRate, c2c, isDemo, settings, landings] = await Promise.all([
    fetchUsdRate(), getC2CFlags(), getDemoStatus(), getSiteSettings(), getLandingList(),
  ]);

  return (
    <div className="space-y-16">
      <JsonLd data={[organizationLd(settings), websiteLd()]} />
      {/* Hero */}
      <section data-on-dark className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-header to-primary px-6 py-14 text-center text-header-foreground md:py-20">
        <Ship
          className="pointer-events-none absolute -right-10 -bottom-10 size-64 text-header-foreground/10"
          strokeWidth={1}
          aria-hidden="true"
        />
        <div className="relative">
          <h1 className="mx-auto mb-4 max-w-3xl text-balance text-3xl font-extrabold tracking-tight md:text-5xl">
            Пригон авто з США під ключ в Україну
          </h1>
          <p className="mx-auto mb-8 max-w-xl text-lg text-header-foreground/90">
            Copart · IAAI · доставка · розмитнення · калькулятор вартості
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <Button asChild size="lg" className="bg-accent px-8 focus-visible:ring-header-foreground text-lg font-bold text-accent-foreground hover:bg-accent/90">
              <Link href="/calculator">
                Порахувати вартість
                <ArrowRight className="size-5" strokeWidth={ICON_STROKE} aria-hidden="true" />
              </Link>
            </Button>
          </div>
          {isDemo === true && (
            <p className="mt-6 text-sm text-warning" data-testid="home-demo-note">
              ⚠ Тестові тарифи — всі розрахунки є демонстраційними
            </p>
          )}
        </div>
      </section>

      {/* Два напрямки — прибирає плутанину між імпортом і локальним каталогом */}
      <section aria-labelledby="directions-heading">
        <h2 id="directions-heading" className={H2}>
          Два напрямки
        </h2>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <Link href="/calculator" className={CARD_LINK}>
            <Card className={CARD_HOVER}>
              <CardContent className="space-y-3">
                <IconTile icon={Ship} />
                <h3 className="text-lg font-bold text-card-foreground transition-colors group-hover:text-primary">
                  Імпорт з аукціонів США
                </h3>
                <p className="text-sm text-muted-foreground">
                  Авто з Copart та IAAI: розрахунок «під ключ», викуп, доставка й розмитнення.
                </p>
              </CardContent>
            </Card>
          </Link>
          {c2c.enabled ? (
            <Link href="/ua" className={CARD_LINK}>
              <Card className={CARD_HOVER}>
                <CardContent className="space-y-3">
                  <IconTile icon={MapPin} />
                  <h3 className="text-lg font-bold text-card-foreground transition-colors group-hover:text-primary">
                    {CATALOG_LABEL}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Оголошення від власників і дилерів по всій Україні.
                    {c2c.postingEnabled ? ' Подати своє — безкоштовно.' : ''}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ) : (
            <Card data-testid="home-ua-soon" className="h-full">
              <CardContent className="space-y-3">
                <IconTile icon={MapPin} />
                <h3 className="text-lg font-bold text-card-foreground">{CATALOG_LABEL} — незабаром</h3>
                <p className="text-sm text-muted-foreground">Каталог авто від власників і дилерів готується до запуску.</p>
              </CardContent>
            </Card>
          )}
        </div>
      </section>

      {/* Як це працює */}
      <section aria-labelledby="how-heading">
        <h2 id="how-heading" className={H2}>
          Як це працює
        </h2>
        <ol className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(s => (
            <li key={s.n}>
              <Card className="h-full">
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex size-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
                      {s.n}
                    </span>
                    <s.icon className="size-6 text-primary" strokeWidth={ICON_STROKE} aria-hidden="true" />
                  </div>
                  <h3 className="font-semibold text-card-foreground">{s.title}</h3>
                  <p className="text-sm text-muted-foreground">{s.text}</p>
                </CardContent>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      {/* Окрема секція зі своїм заголовком, поза «Як це працює». null/порожній список — блоку немає */}
      <PopularModels models={landings} limit={POPULAR_LANDINGS_LIMIT} showAll />

      {/* Що входить у розрахунок */}
      <section aria-labelledby="cost-heading">
        <Card>
          <CardContent className="md:px-8">
            <h2 id="cost-heading" className="mb-2 text-2xl font-bold tracking-tight text-card-foreground">
              Що входить у розрахунок
            </h2>
            <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
              Калькулятор розкладає суму на статті — без прихованих рядків. Кожен розрахунок зберігає
              знімок застосованих ставок і курсу, тож до нього можна повернутися пізніше.
            </p>
            <ul className="grid grid-cols-1 gap-x-8 gap-y-3 md:grid-cols-2">
              {COST_ITEMS.map(item => (
                <li key={item} className="flex items-start gap-3 text-sm text-card-foreground">
                  <Check className="mt-0.5 size-5 shrink-0 text-success" strokeWidth={ICON_STROKE} aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Button asChild size="lg" className="font-semibold">
                <Link href="/calculator">Відкрити калькулятор</Link>
              </Button>
              {usdRate && (
                <p className="text-sm text-muted-foreground">
                  Курс НБУ на {usdRate.date}:{' '}
                  <strong className="font-mono text-foreground">{usdRate.rate} грн/$</strong>
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
