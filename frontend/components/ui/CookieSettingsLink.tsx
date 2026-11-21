'use client';
import { openConsentSettings } from '@/lib/consent';
import { COOKIE_SETTINGS_LABEL } from '@/lib/labels';

/** Кнопка в футері: відкриває панель вибору cookie поверх сторінки, без переходу. */
export default function CookieSettingsLink() {
  return (
    <button
      type="button"
      onClick={openConsentSettings}
      className="inline-flex items-center min-h-11 hover:text-footer-foreground hover:underline transition-colors"
    >
      {COOKIE_SETTINGS_LABEL}
    </button>
  );
}
