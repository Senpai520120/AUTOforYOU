import { serverGet } from '@/lib/server-api';
import type { FaqEntry, HowItWorksData } from '@/lib/types';

/** «Як працює пригон» + FAQ (задача 2.13). null — API недоступне. */
export async function getHowItWorks(revalidate = 60): Promise<HowItWorksData | null> {
  return serverGet<HowItWorksData>('/api/v1/content/how-it-works/', revalidate);
}

/** FAQ для сторінки калькулятора. null — API недоступне. */
export async function getCalculatorFaq(revalidate = 60): Promise<FaqEntry[] | null> {
  const data = await serverGet<{ faq: FaqEntry[] }>('/api/v1/content/faq/?place=calculator', revalidate);
  return data ? data.faq : null;
}

/** Чи опубліковано сторінку; збій API = «ні» (посилання в підвалі й sitemap не з'являються). */
export async function isHowItWorksPublished(revalidate = 60): Promise<boolean> {
  return (await getHowItWorks(revalidate))?.published === true;
}
