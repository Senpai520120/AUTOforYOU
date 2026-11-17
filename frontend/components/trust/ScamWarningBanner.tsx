'use client';
import Link from 'next/link';
import { useSiteConfig } from '@/lib/use-site-config';
import { SAFE_DEAL_RULES_LABEL } from '@/lib/labels';

/**
 * Банер «не вносьте передоплату» (задача 8.6). Текст — SiteSettings.prepayment_warning_text
 * (правиться в адмінці); порожній текст або недоступне API — банер не показується.
 * Не закривається і не вимагає позначки.
 */
export default function ScamWarningBanner({ className = '' }: { className?: string }) {
  const config = useSiteConfig();
  const text = config?.prepayment_warning_text?.trim();
  if (!text) return null;
  return (
    <div
      role="note"
      data-testid="scam-warning"
      className={`rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 ${className}`}
    >
      <p>
        <span aria-hidden="true">⚠ </span>
        {text}
      </p>
      <Link href="/rules" className="mt-1 inline-block font-semibold text-amber-900 underline hover:no-underline">
        {SAFE_DEAL_RULES_LABEL}
      </Link>
    </div>
  );
}
