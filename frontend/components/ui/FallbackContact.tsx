'use client';
/**
 * Запасний вихід, коли онлайн-шлях до заявки недоступний (задача 10.7):
 * контакти з SiteSettings (без хардкоду) і кнопка «Спробувати ще раз».
 * Без контактів — чесний текст без вигаданих номерів і обіцянок передзвону.
 */
import { useEffect, useState } from 'react';
import { fetchSiteSettings } from '@/lib/site-settings-client';
import { Button } from '@/components/shadcn/button';
import type { SiteSettings } from '@/lib/types';

export const NO_CONTACT_TEXT = 'Зараз ми не можемо прийняти заявку онлайн. Спробуйте ще раз трохи пізніше.';

export interface ContactLink { key: string; label: string; href?: string }

/** Непорожні контакти у порядку: телефон, менеджер, email, Telegram-бот, канал. */
export function contactLinks(s: SiteSettings | null | undefined): ContactLink[] {
  if (!s) return [];
  const out: ContactLink[] = [];
  const phone = s.phone?.trim();
  if (phone) out.push({ key: 'phone', label: phone, href: `tel:${phone.replace(/[^\d+]/g, '')}` });
  const manager = s.manager_contact?.trim();
  if (manager) out.push({ key: 'manager', label: manager });
  const email = s.support_email?.trim();
  if (email) out.push({ key: 'email', label: email, href: `mailto:${email}` });
  const bot = s.telegram_bot_username?.trim().replace(/^@/, '');
  if (bot && /^[A-Za-z0-9_]+$/.test(bot)) {
    out.push({ key: 'bot', label: `Telegram: @${bot}`, href: `https://t.me/${bot}` });
  }
  const channel = s.telegram_channel_url?.trim();
  if (channel && /^https:\/\/t\.me\//.test(channel)) {
    out.push({ key: 'channel', label: 'Telegram-канал', href: channel });
  }
  return out;
}

/** Завантажує публічні налаштування, коли active=true (одноразово на вхід у стан). */
export function useFallbackSettings(active: boolean): SiteSettings | null {
  const [settings, setSettings] = useState<SiteSettings | null>(null);
  useEffect(() => {
    if (!active) return;
    let alive = true;
    fetchSiteSettings()
      .then((s) => { if (alive) setSettings(s); })
      .catch(() => { if (alive) setSettings(null); });
    return () => { alive = false; };
  }, [active]);
  return settings;
}

interface Props {
  settings: SiteSettings | null;
  /** Без onRetry кнопки немає (напр. контакт під помилкою розрахунку). */
  onRetry?: () => void;
  retrying?: boolean;
}

/** Лише контакти (без кнопки повтору і без тексту про недоступність); null, якщо контактів немає. */
export function ContactList({ settings, title = "Зв'яжіться з нами напряму:" }: { settings: SiteSettings | null; title?: string }) {
  const links = contactLinks(settings);
  if (links.length === 0) return null;
  return (
    <div data-testid="fallback-contact">
      <p className="text-sm text-foreground">{title}</p>
      <ul className="mt-1 space-y-1 text-sm">
        {links.map((l) => (
          <li key={l.key}>
            {l.href ? (
              <a href={l.href} className="text-primary underline underline-offset-4"
                {...(l.href.startsWith('https:') ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
                {l.label}
              </a>
            ) : (
              <span className="text-foreground">{l.label}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function FallbackContact({ settings, onRetry, retrying = false }: Props) {
  const links = contactLinks(settings);
  return (
    <div className="mt-3">
      {links.length > 0 ? (
        <ContactList settings={settings} />
      ) : (
        <p data-testid="fallback-no-contact" className="text-sm text-foreground">{NO_CONTACT_TEXT}</p>
      )}
      {onRetry && (
        <Button type="button" variant="outline" onClick={onRetry} disabled={retrying} aria-busy={retrying} className="mt-3 font-semibold">
          {retrying ? 'Завантажую…' : 'Спробувати ще раз'}
        </Button>
      )}
    </div>
  );
}
