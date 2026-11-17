import Link from 'next/link';
import CookieSettingsLink from '@/components/ui/CookieSettingsLink';
import { getSiteConfig, getDemoStatus } from '@/lib/site-config';
import { ownerTitle } from '@/lib/site-settings';
import { isHowItWorksPublished } from '@/lib/content';
import { FAQ_LABEL, HOW_IT_WORKS_LABEL } from '@/lib/labels';

/** Серверний підвал: реквізити з налаштувань сайту; при недоступному API — без них. */
export default async function Footer() {
  const [s, isDemo, trustPages] = await Promise.all([getSiteConfig(60), getDemoStatus(), isHowItWorksPublished()]);
  const owner = ownerTitle(s);
  const tgUrl = s?.telegram_channel_url && /^https:\/\/t\.me\//.test(s.telegram_channel_url) ? s.telegram_channel_url : '';
  const botUrl = s?.telegram_bot_username ? `https://t.me/${s.telegram_bot_username}` : '';
  const contacts = [s?.support_email, s?.phone, s?.owner_address].filter(Boolean) as string[];

  return (
    <footer className="bg-slate-900 text-slate-400 mt-auto py-8">
      <div className="max-w-7xl mx-auto px-4 text-center text-sm">
        {/* Футер показується і на /ua — сторінці локальних оголошень, тому опис
            покриває обидва напрямки, а не тільки імпорт. */}
        <p className="font-semibold text-white mb-1">AUTOforYOU</p>
        <p>Авто з аукціонів США під ключ{s?.c2c_enabled === true ? ' · Оголошення по Україні' : ''}</p>
        {(owner || contacts.length > 0 || tgUrl || botUrl) && (
          <p className="mt-2 text-xs text-slate-400" data-testid="footer-requisites">
            {owner && <span>{owner}{s?.owner_code ? `, код ${s.owner_code}` : ''}</span>}
            {contacts.map((c) => (
              <span key={c}>{owner || c !== contacts[0] ? ' · ' : ''}{c}</span>
            ))}
            {tgUrl && (
              <>
                {' · '}
                <a
                  href={tgUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-slate-300 transition-colors"
                >
                  Telegram
                </a>
              </>
            )}
            {botUrl && (
              <>
                {' · '}
                <a
                  href={botUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-slate-300 transition-colors"
                >
                  Telegram-бот
                </a>
              </>
            )}
          </p>
        )}
        {trustPages && (
          <nav aria-label="Інформація про пригон" className="mt-4 flex justify-center gap-5 text-xs text-slate-400 flex-wrap">
            <Link href="/how-it-works" className="hover:text-slate-300 transition-colors">{HOW_IT_WORKS_LABEL}</Link>
            <Link href="/how-it-works#faq-block-title" className="hover:text-slate-300 transition-colors">{FAQ_LABEL}</Link>
          </nav>
        )}
        <nav aria-label="Юридичні документи" className="mt-4 flex justify-center gap-5 text-xs text-slate-400 flex-wrap">
          <Link href="/terms" className="hover:text-slate-300 transition-colors">Умови використання</Link>
          <Link href="/rules" className="hover:text-slate-300 transition-colors">Правила розміщення</Link>
          <Link href="/refund" className="hover:text-slate-300 transition-colors">Повернення коштів</Link>
          <Link href="/privacy" className="hover:text-slate-300 transition-colors">Конфіденційність</Link>
          <Link href="/cookies" className="hover:text-slate-300 transition-colors">Cookie</Link>
          <CookieSettingsLink />
        </nav>
        <p className="mt-3 text-xs text-slate-400">
          Послугу пригону надає партнер, а не AUTOforYOU
        </p>
        {isDemo === true && (
          <p className="mt-1 text-xs text-slate-400" data-testid="footer-demo-note">
            Тестові тарифи — всі розрахунки є демонстраційними
          </p>
        )}
      </div>
    </footer>
  );
}
