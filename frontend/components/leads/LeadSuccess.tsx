'use client';
import { ContactList } from '@/components/ui/FallbackContact';
import type { SiteSettings } from '@/lib/types';
import { CircleCheck } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { ICON_STROKE } from '@/lib/utils';

const MAX_STEPS = 6;

/** Кроки «що далі»: по рядку, порожні відкидаються, максимум 6. */
export function parseNextSteps(raw: string | undefined | null): string[] {
  return (raw ?? '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean).slice(0, MAX_STEPS);
}

interface Props {
  settings?: SiteSettings | null;
  publicId: string;
  onNew?: () => void;
  newLabel?: string;
}

export default function LeadSuccess({ publicId, onNew, newLabel = 'Новий розрахунок', settings = null }: Props) {
  const hours = settings?.lead_response_hours ?? null;
  const steps = parseNextSteps(settings?.lead_next_steps);
  return (
    <div role="status" data-testid="lead-success" className="text-center py-6">
      <CircleCheck className="mx-auto mb-3 size-12 text-success" strokeWidth={ICON_STROKE} aria-hidden="true" />
      <h3 className="text-xl font-bold text-foreground mb-2">Заявку №{publicId} отримано</h3>
      <p className="text-muted-foreground text-sm mb-2">
        Брокер зв&apos;яжеться з вами найближчим часом зручним для вас способом.
      </p>
      {hours !== null && hours > 0 && (
        <p data-testid="lead-response-time" className="text-foreground text-sm font-semibold mb-2">
          Ми відповімо протягом {hours} год
        </p>
      )}
      {steps.length > 0 && (
        <div className="text-left max-w-md mx-auto mb-4">
          <p className="text-sm font-semibold text-foreground mb-1">Що буде далі</p>
          <ol data-testid="lead-next-steps" className="list-decimal pl-5 text-sm text-foreground space-y-1">
            {steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}
      <p className="text-foreground text-sm mb-5">
        Назвіть менеджеру код <span className="font-mono font-bold">{publicId}</span>.
      </p>
      <div className="mb-4 text-left max-w-md mx-auto"><ContactList settings={settings} /></div>
      {onNew && (
        <Button type="button" size="lg" onClick={onNew} className="px-6 font-semibold">
          {newLabel}
        </Button>
      )}
    </div>
  );
}
