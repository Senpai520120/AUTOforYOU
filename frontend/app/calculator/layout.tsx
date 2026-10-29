import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';

// демо-тарифи — не індексувати до реальних ставок (noindex лишається, OG-теги потрібні для превью ссилки)
export const metadata: Metadata = buildMetadata({
  title: 'Калькулятор вартості',
  description: 'Розрахуйте повну вартість авто з аукціонів США під ключ: аукціонний збір, доставка, розмитнення, акциз, мито, ПДВ, пенсійний збір.',
  path: '/calculator',
  noindex: true,
  ownImage: true,
});

export default function CalculatorLayout({ children }: { children: React.ReactNode }) {
  return children;
}
