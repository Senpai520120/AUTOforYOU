import type { ReactNode } from 'react';
import type { SiteSettings } from '@/lib/types';
import { NOT_FILLED, OWNER_NOT_CONFIGURED, formatDocDate, ownerTitle } from '@/lib/site-settings';

interface Props {
  title: string;
  settings: SiteSettings | null;
  /** Показати блок «Власник персональних даних» над текстом. */
  showOwner?: boolean;
  children: ReactNode;
}

/** Реквізити власника: або дані з налаштувань, або чесна заглушка. */
export function OwnerDetails({ settings }: { settings: SiteSettings | null }) {
  if (!settings?.owner_configured) {
    return <span data-testid="owner-missing">{OWNER_NOT_CONFIGURED}</span>;
  }
  return (
    <span data-testid="owner-details">
      <strong>{ownerTitle(settings)}</strong>, код {settings.owner_code}, {settings.owner_address}
    </span>
  );
}

/** Email-посилання або «не заповнено». */
export function EmailOrMissing({ email }: { email: string }) {
  if (!email) return <span className="text-slate-500">{NOT_FILLED}</span>;
  return (
    <a href={`mailto:${email}`} className="font-mono text-blue-600 hover:underline">
      {email}
    </a>
  );
}

export default function LegalPage({ title, settings, showOwner = true, children }: Props) {
  const approved = settings?.legal_docs_approved === true;
  const date = formatDocDate(settings?.legal_docs_updated_at);
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      {!approved && (
        <p
          data-testid="legal-template-badge"
          className="text-xs bg-amber-50 border border-amber-300 text-amber-800 rounded-lg px-4 py-2 mb-8"
        >
          Шаблон — потребує перевірки юристом перед публікацією
        </p>
      )}
      <h1 className="text-3xl font-bold text-slate-900 mb-8">{title}</h1>

      {showOwner && (
        <div className="mb-8 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          <p className="font-semibold text-slate-800 mb-1">Власник персональних даних</p>
          <OwnerDetails settings={settings} />
        </div>
      )}

      <div className="prose prose-slate max-w-none space-y-6 text-slate-700">
        {children}
        <p className="text-xs text-slate-400 mt-10 border-t pt-4">
          Останнє оновлення: {date || NOT_FILLED}
        </p>
      </div>
    </div>
  );
}
