'use client';
import { useEffect, useState } from 'react';
import { fetchSiteSettings } from '@/lib/site-settings-client';
import type { SiteSettings } from '@/lib/types';

/** Публічні налаштування для клієнтських сторінок. undefined — ще вантажиться, null — недоступні. */
export function useSiteConfig(): SiteSettings | null | undefined {
  const [config, setConfig] = useState<SiteSettings | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    fetchSiteSettings()
      .then((d) => alive && setConfig(d))
      .catch(() => alive && setConfig(null));
    return () => {
      alive = false;
    };
  }, []);
  return config;
}
