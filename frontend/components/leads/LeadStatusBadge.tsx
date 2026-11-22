import { leadStatusLabel } from '@/lib/labels';
import type { LeadStatus } from '@/lib/types';

const COLORS: Record<LeadStatus, string> = {
  new: 'bg-warning/15 text-foreground',
  in_progress: 'bg-link/10 text-link',
  contract: 'bg-primary/10 text-foreground',
  car_bought: 'bg-secondary text-foreground border border-border',
  in_transit: 'bg-link/10 text-foreground border border-link/40',
  customs: 'bg-warning/15 text-foreground border border-warning',
  delivered: 'bg-success/10 text-success',
  rejected: 'bg-muted text-muted-foreground',
  spam: 'bg-destructive/10 text-destructive',
};

export default function LeadStatusBadge({ status, label }: { status: LeadStatus; label?: string }) {
  return (
    <span data-testid="lead-status" className={`inline-block text-xs px-2 py-1 rounded font-semibold ${COLORS[status] ?? 'bg-muted text-foreground'}`}>
      {leadStatusLabel(status, label)}
    </span>
  );
}
