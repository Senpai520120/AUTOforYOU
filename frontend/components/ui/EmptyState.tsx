import Link from 'next/link';
import type { ReactNode } from 'react';

interface Props {
  title: string;
  hint?: string;
  icon?: ReactNode;
  action?: { label: string; href?: string; onClick?: () => void };
}

/** Порожній стан: заголовок, підказка, необов'язкова дія. Помилку завантаження ним не показувати. */
export default function EmptyState({ title, hint, icon, action }: Props) {
  const cls = 'mt-3 inline-flex min-h-11 items-center text-sm font-medium text-primary underline underline-offset-4 hover:text-primary/80';
  return (
    <div className="rounded-xl border border-dashed border-input bg-card p-10 text-center text-muted-foreground">
      {icon && <div className="mb-3 flex justify-center text-4xl" aria-hidden="true">{icon}</div>}
      <p className="text-base font-semibold text-foreground">{title}</p>
      {hint && <p className="mt-1 text-sm">{hint}</p>}
      {action?.href && <Link href={action.href} className={cls}>{action.label}</Link>}
      {action && !action.href && <button type="button" onClick={action.onClick} className={cls}>{action.label}</button>}
    </div>
  );
}
