import { OG_CONTENT_TYPE, OG_SIZE } from '@/lib/og';
import { renderLocalListingImage } from './opengraph-image';

// 6.3b: twitter:image — та сама картка, що й og:image.
export const alt = 'Оголошення про продаж авто';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
export const dynamic = 'force-dynamic';  // превʼю не старше самої сторінки (6.3b)

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return renderLocalListingImage(id);
}
