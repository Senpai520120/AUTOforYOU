import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Калькулятор вартості',
  description: 'Розрахуйте повну вартість авто з аукціонів США під ключ: аукціонний збір, доставка, розмитнення, акциз, мито, ПДВ, пенсійний збір.',
  robots: { index: false }, // демо-тарифи — не індексувати до реальних ставок
};

export default function CalculatorLayout({ children }: { children: React.ReactNode }) {
  return children;
}
