import Link from 'next/link';
import CookieSettingsLink from '@/components/ui/CookieSettingsLink';
import { getSiteConfig, getDemoStatus } from '@/lib/site-config';
import { ownerTitle, partnerPhrase } from '@/lib/site-settings';
import { getAbout } from '@/lib/about';
import { isHowItWorksPublished } from '@/lib/content';
import { hasLandings } from '@/lib/landings';
import { ABOUT_LABEL, CATALOG_LABEL, FAQ_LABEL, HOW_IT_WORKS_LABEL, LANDING_INDEX_LABEL } from '@/lib/labels';

/** Серверний підвал: реквізити з налаштувань сайту; при недоступному API — без них. */
export default async function Footer() {
  const [s, isDemo, trustPages, landings] = await Promise.all([
    getSiteConfig(60), getDemoStatus(), isHowItWorksPublished(), hasLandings(),
  ]);
  const hasAbout = !!s?.about_text?.trim();
  const owner = ownerTitle(s);
  const tgUrl = s?.telegram_channel_url && /^https:\/\/t\.me\//.test(s.telegram_channel_url) ? s.telegram_channel_url : '';
  const botUrl = s?.telegram_bot_username ? `https://t.me/${s.telegram_bot_username}` : '';
  const contacts = [s?.support_email, s?.phone, s?.owner_address].filter(Boolean) as string[];
  // Роздільники ставляться лише між наявними пунктами: прихований пункт не лишає «·» навислим.
  const requisites: { key: string; text: string; href?: string }[] = [
    ...(owner ? [{ key: 'owner', text: `${owner}${s?.owner_code ? `, код ${s.owner_code}` : ''}` }] : []),
    ...contacts.map((c) => ({ key: `c-${c}`, text: c })),
    ...(tgUrl ? [{ key: 'tg', text: 'Telegram', href: tgUrl }] : []),
    ...(botUrl ? [{ key: 'bot', text: 'Telegram-бот', href: botUrl }] : []),
  ];

  return (
    <footer data-on-dark className="bg-footer text-footer-muted mt-auto py-8">
      <div className="max-w-7xl mx-auto px-4 text-center text-sm">
        {/* Футер показується і на /ua — сторінці локальних оголошень, тому опис
            покриває обидва напрямки, а не тільки імпорт. */}
        <p className="font-semibold text-footer-foreground mb-1">AUTOforYOU</p>
        <p>Авто з аукціонів США під ключ{s?.c2c_enabled === true ? ` · ${CATALOG_LABEL}` : ''}</p>
        {requisites.length > 0 && (
          <ul className="mt-2 flex flex-wrap justify-center items-center text-xs text-footer-muted" data-testid="footer-requisites">
            {requisites.map((r, i) => (
              <li key={r.key} className="inline-flex items-center">
                {i > 0 && <span aria-hidden="true" className="mx-2">·</span>}
                {r.href ? (
                  <a
                    href={r.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors"
                  >
                    {r.text}
                  </a>
                ) : r.text}
              </li>
            ))}
          </ul>
        )}
        {(trustPages || landings || hasAbout) && (
          <nav aria-label="Інформація про пригон" className="mt-4 flex justify-center items-center gap-x-5 text-xs text-footer-muted flex-wrap">
            {trustPages && <Link href="/how-it-works" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors">{HOW_IT_WORKS_LABEL}</Link>}
            {landings && <Link href="/prigon" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors" data-testid="footer-link-prigon">{LANDING_INDEX_LABEL}</Link>}
            {hasAbout && <Link href="/about" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors" data-testid="footer-link-about">{ABOUT_LABEL}</Link>}
            {trustPages && <Link href="/how-it-works#faq-block-title" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors">{FAQ_LABEL}</Link>}
          </nav>
        )}
        <nav aria-label="Юридичні документи" className="mt-4 flex justify-center items-center gap-x-5 text-xs text-footer-muted flex-wrap">
          <Link href="/terms" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors">Умови використання</Link>
          <Link href="/rules" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors">Правила розміщення</Link>
          <Link href="/refund" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors">Повернення коштів</Link>
          <Link href="/privacy" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors">Конфіденційність</Link>
          <Link href="/cookies" className="inline-flex items-center min-h-11 hover:text-footer-foreground transition-colors">Cookie</Link>
          <CookieSettingsLink />
        </nav>
        <p className="mt-3 text-xs text-footer-muted">
          {partnerPhrase(s?.partner_name)}
        </p>
        {isDemo === true && (
          <p className="mt-1 text-xs text-footer-muted" data-testid="footer-demo-note">
            Тестові тарифи — всі розрахунки є демонстраційними
          </p>
        )}
      </div>
    </footer>
  );
}
