import PopularModels from '@/components/landing/PopularModels';
import type { LandingListItem } from '@/lib/types';

/** «Схожі моделі» на лендингу: тот самий блок посилань, свій заголовок і testid. Немає моделей — немає блоку. */
export default function SimilarModels({ models }: { models: LandingListItem[] }) {
  return <PopularModels models={models} title="Схожі моделі" testId="similar-models" />;
}
