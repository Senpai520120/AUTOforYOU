'use client';
import { useSiteConfig } from '@/lib/use-site-config';
import PartnerVinLink from '@/components/calculator/PartnerVinLink';

const MAX_TIPS = 10;

export function parseCheckTips(raw: string | undefined | null): string[] {
  return (raw ?? '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean).slice(0, MAX_TIPS);
}

/**
 * Поради «Як перевірити авто перед купівлею» (задача 10.29) на картці оголошення.
 * Текст пише власник в адмінці (SiteSettings.listing_check_tips), у коді його немає.
 * Порожньо або API недоступне — блоку немає.
 * Місце під VIN-перевірку: партнерське посилання з налаштувань (PartnerVinLink); поки URL не заданий —
 * нічого не показується. Заморожений розділ /vin-check не відкривається.
 */
export default function ListingCheckTips() {
  const config = useSiteConfig();
  const tips = parseCheckTips(config?.listing_check_tips);
  return (
    <>
      {tips.length > 0 && (
    <section data-testid="listing-check-tips" aria-labelledby="check-tips-title" className="mt-8">
      <h2 id="check-tips-title" className="text-lg font-bold text-foreground mb-3">Як перевірити авто перед купівлею</h2>
      <ul className="bg-card border rounded-xl p-4 text-sm text-foreground list-disc pl-8 space-y-1">
        {tips.map((t, i) => <li key={i}>{t}</li>)}
      </ul>
    </section>
      )}
      <PartnerVinLink />
    </>
  );
}
