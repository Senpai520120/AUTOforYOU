import { getSiteSettings } from '@/lib/site-settings';

/** Текст «Про нас» з налаштувань сайту. Порожньо або збій API = null (сторінки й посилань немає). */
export async function getAbout(revalidate = 60): Promise<string | null> {
  const text = (await getSiteSettings(revalidate))?.about_text?.trim();
  return text ? text : null;
}
