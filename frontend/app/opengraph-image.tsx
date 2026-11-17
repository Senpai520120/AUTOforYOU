import { brandCard, OG_CONTENT_TYPE, OG_SIZE } from '@/lib/og-card';

// Бренд-картинка за замовчуванням: покриває всі сегменти без власної (/listings, /ua, юр. сторінки...). Без цифр ставок.
export const alt = 'AUTOforYOU - авто з США під ключ';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default async function Image() {
  return brandCard();
}
