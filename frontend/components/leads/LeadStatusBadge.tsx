import { leadStatusLabel } from '@/lib/labels';
import type { LeadStatus } from '@/lib/types';

const COLORS: Record<LeadStatus, string> = {
  new: 'bg-amber-100 text-amber-800',
  in_progress: 'bg-blue-100 text-blue-800',
  contract: 'bg-indigo-100 text-indigo-800',
  car_bought: 'bg-violet-100 text-violet-800',
  in_transit: 'bg-cyan-100 text-cyan-800',
  customs: 'bg-orange-100 text-orange-800',
  delivered: 'bg-green-100 text-green-800',
  rejected: 'bg-slate-200 text-slate-700',
  spam: 'bg-red-100 text-red-800',
};

export default function LeadStatusBadge({ status, label }: { status: LeadStatus; label?: string }) {
  return (
    <span data-testid="lead-status" className={`inline-block text-xs px-2 py-1 rounded font-semibold ${COLORS[status] ?? 'bg-slate-100 text-slate-700'}`}>
      {leadStatusLabel(status, label)}
    </span>
  );
}
