import { BRAND_ALT, OG_CONTENT_TYPE, OG_SIZE, brandImage } from '@/lib/og';

// 6.3b: бренд-картка за замовчуванням — для всіх сторінок без власного превʼю (статична).
export const alt = BRAND_ALT;
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
  return brandImage();
}
