'use client';
import { useEffect, useState } from 'react';
import { apiGet } from '@/api/client';
import type { SiteSettings } from '@/lib/types';

/** Публічні налаштування для клієнтських сторінок. undefined — ще вантажиться, null — недоступні. */
export function useSiteConfig(): SiteSettings | null | undefined {
  const [config, setConfig] = useState<SiteSettings | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    apiGet<SiteSettings>('/api/v1/site-settings/')
      .then((d) => alive && setConfig(d))
      .catch(() => alive && setConfig(null));
    return () => {
      alive = false;
    };
  }, []);
  return config;
}
