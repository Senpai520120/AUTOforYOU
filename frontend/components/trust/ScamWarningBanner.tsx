'use client';
import Link from 'next/link';
import { TriangleAlert } from 'lucide-react';
import { ICON_STROKE } from '@/lib/utils';
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
      className={`flex items-start gap-2 rounded-lg border border-warning bg-warning/15 p-3 text-xs text-foreground ${className}`}
    >
      <TriangleAlert className="mt-0.5 size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
      <div>
        <p>{text}</p>
        <Link href="/rules" className="mt-1 inline-block font-semibold text-foreground underline hover:no-underline">
          {SAFE_DEAL_RULES_LABEL}
        </Link>
      </div>
    </div>
  );
}
