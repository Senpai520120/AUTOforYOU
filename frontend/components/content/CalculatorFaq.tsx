'use client';
import { useEffect, useState } from 'react';
import FaqBlock from '@/components/content/FaqBlock';
import { API_URL } from '@/lib/config';
import type { FaqEntry } from '@/lib/types';

/** FAQ під калькулятором: порожньо або збій API — блок не показується (задача 2.13). */
export default function CalculatorFaq() {
  const [items, setItems] = useState<FaqEntry[]>([]);

  useEffect(() => {
    let alive = true;
    fetch(`${API_URL}/api/v1/content/faq/?place=calculator`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { faq?: FaqEntry[] } | null) => {
        if (alive && data && Array.isArray(data.faq)) setItems(data.faq);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  return <FaqBlock items={items} testId="calculator-faq" />;
}
