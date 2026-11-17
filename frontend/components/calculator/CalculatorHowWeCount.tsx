import Link from 'next/link';
import { HOW_IT_WORKS_LABEL } from '@/lib/labels';

/**
 * «Як рахуємо» під калькулятором (9.54): що входить у розрахунок і звідки ставки.
 * Без цифр і обіцянок: суми, дата ставок і перелік «що не входить» приходять з API разом із результатом.
 */
export default function CalculatorHowWeCount() {
  return (
    <section className="mt-10" data-testid="calculator-how-we-count" aria-labelledby="how-we-count-title">
      <h2 id="how-we-count-title" className="font-semibold text-slate-900 mb-2">Як рахуємо</h2>
      <p className="text-sm text-slate-700">
        Вартість «під ключ» складається з ціни на аукціоні, аукціонного збору, доставки по США та морського
        фрахту, а також митних платежів в Україні: акцизу, мита, ПДВ і пенсійного збору. Ставки беруться з
        таблиць аукціонів і митних правил, дату аукціонних ставок показано під результатом. Розрахунок
        орієнтовний: остаточну суму підтверджує митний брокер.
      </p>
      <p className="mt-3 text-sm">
        <Link href="/how-it-works" className="text-blue-700 underline">{HOW_IT_WORKS_LABEL}</Link>
        {' · '}
        <Link href="/prigon" className="text-blue-700 underline" data-testid="calc-link-prigon">Пригон за моделями</Link>
      </p>
    </section>
  );
}
