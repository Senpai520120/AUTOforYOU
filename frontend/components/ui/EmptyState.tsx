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
  const cls = 'mt-3 inline-block text-blue-600 hover:underline text-sm';
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-slate-400">
      {icon && <div className="text-4xl mb-2">{icon}</div>}
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="text-xs mt-1">{hint}</p>}
      {action?.href && <Link href={action.href} className={cls}>{action.label}</Link>}
      {action && !action.href && <button type="button" onClick={action.onClick} className={cls}>{action.label}</button>}
    </div>
  );
}
