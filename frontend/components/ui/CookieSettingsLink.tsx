'use client';
import { openConsentSettings } from '@/lib/consent';
import { COOKIE_SETTINGS_LABEL } from '@/lib/labels';

/** Кнопка в футері: відкриває панель вибору cookie поверх сторінки, без переходу. */
export default function CookieSettingsLink() {
  return (
    <button
      type="button"
      onClick={openConsentSettings}
      className="hover:text-slate-300 transition-colors"
    >
      {COOKIE_SETTINGS_LABEL}
    </button>
  );
}
