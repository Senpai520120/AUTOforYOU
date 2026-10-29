import { brandCard, OG_CONTENT_TYPE, OG_SIZE } from '@/lib/og-card';

export const alt = 'Калькулятор вартості авто з США - AUTOforYOU';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default async function Image() {
  return brandCard('Калькулятор вартості авто з США', 'Повна вартість під ключ: збори, доставка, розмитнення');
}
