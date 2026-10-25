'use client';
import { useEffect, useState } from 'react';
import { apiGet } from '@/api/client';
import type { SiteSettings } from '@/lib/types';

/**
 * Партнерське посилання carVertical (задача 3.2a). Адресу віддає публічний /api/v1/site-settings/
 * (змінна CARVERTICAL_PARTNER_URL у .env бекенда): у коді домену немає. Порожньо, помилка API
 * або не https — блоку немає. Це звичайне посилання, ПДн не передаються.
 */
export default function PartnerVinLink() {
  const [url, setUrl] = useState('');

  useEffect(() => {
    let alive = true;
    apiGet<SiteSettings>('/api/v1/site-settings/')
      .then((s) => {
        const value = typeof s?.carvertical_partner_url === 'string' ? s.carvertical_partner_url : '';
        if (alive && value.startsWith('https://')) setUrl(value);
      })
      .catch(() => { /* без налаштувань посилання просто не показуємо */ });
    return () => { alive = false; };
  }, []);

  if (!url) return null;
  return (
    <p data-testid="partner-vin-link" className="mt-6 text-sm text-slate-700">
      <a href={url} target="_blank" rel="sponsored noopener noreferrer"
         className="text-blue-700 underline hover:text-blue-900">
        Перевірити авто за VIN (carVertical)
      </a>{' '}
      <span className="text-xs text-slate-500">партнерське посилання</span>
    </p>
  );
}
