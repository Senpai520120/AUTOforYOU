'use client';
import { useEffect, useState } from 'react';
import { fetchSiteSettings } from '@/lib/site-settings-client';

/**
 * Партнерське посилання carVertical (задача 3.2a). Адресу віддає публічний /api/v1/site-settings/
 * (змінна CARVERTICAL_PARTNER_URL у .env бекенда): у коді домену немає. Порожньо, помилка API
 * або не https — блоку немає. Це звичайне посилання, ПДн не передаються.
 */
export default function PartnerVinLink() {
  const [url, setUrl] = useState('');

  useEffect(() => {
    let alive = true;
    fetchSiteSettings()
      .then((s) => {
        const value = typeof s?.carvertical_partner_url === 'string' ? s.carvertical_partner_url : '';
        if (alive && value.startsWith('https://')) setUrl(value);
      })
      .catch(() => { /* без налаштувань посилання просто не показуємо */ });
    return () => { alive = false; };
  }, []);

  if (!url) return null;
  return (
    <p data-testid="partner-vin-link" className="mt-6 text-sm text-card-foreground">
      <a href={url} target="_blank" rel="sponsored noopener noreferrer"
         className="text-link underline underline-offset-4 hover:text-link/80">
        Перевірити авто за VIN (carVertical)
      </a>{' '}
      <span className="text-xs text-muted-foreground">партнерське посилання</span>
    </p>
  );
}
