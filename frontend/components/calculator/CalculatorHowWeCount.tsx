'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { apiGet } from '@/api/client';
import type { HowItWorksData } from '@/lib/types';
import { HOW_IT_WORKS_LABEL } from '@/lib/labels';

/**
 * «Як рахуємо» під калькулятором (9.54): що входить у розрахунок і звідки ставки.
 * Без цифр і обіцянок: суми, дата ставок і перелік «що не входить» приходять з API разом із результатом.
 */
export default function CalculatorHowWeCount() {
  // Посилання на «Як працює пригон» лише коли розділ опубліковано; збій API = без посилання.
  const [howItWorksOn, setHowItWorksOn] = useState(false);
  useEffect(() => {
    let alive = true;
    apiGet<HowItWorksData>('/api/v1/content/how-it-works/')
      .then((d) => { if (alive) setHowItWorksOn(d.published === true); })
      .catch(() => { if (alive) setHowItWorksOn(false); });
    return () => { alive = false; };
  }, []);
  return (
    <section className="mt-10" data-testid="calculator-how-we-count" aria-labelledby="how-we-count-title">
      <h2 id="how-we-count-title" className="text-xl font-bold tracking-tight text-foreground mb-3">Як рахуємо</h2>
      <p className="text-sm text-muted-foreground">
        Вартість «під ключ» складається з ціни на аукціоні, аукціонного збору, доставки по США та морського
        фрахту, а також митних платежів в Україні: акцизу, мита, ПДВ і пенсійного збору. Ставки беруться з
        таблиць аукціонів і митних правил, дату аукціонних ставок показано під результатом. Розрахунок
        орієнтовний: остаточну суму підтверджує митний брокер.
      </p>
      <p className="mt-3 text-sm">
        {howItWorksOn && (
          <>
            <Link href="/how-it-works" className="text-primary underline underline-offset-4 hover:text-primary/80" data-testid="calc-link-how-it-works">{HOW_IT_WORKS_LABEL}</Link>
            {' · '}
          </>
        )}
        <Link href="/prigon" className="text-primary underline underline-offset-4 hover:text-primary/80" data-testid="calc-link-prigon">Пригон за моделями</Link>
      </p>
    </section>
  );
}
