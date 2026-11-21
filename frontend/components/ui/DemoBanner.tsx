import { TriangleAlert } from 'lucide-react';
import { ICON_STROKE } from '@/lib/utils';

// Демо-банер (2.6): показується за is_demo з API — коли всі тарифи позначені перевіреними, зникає сам,
// без перебудови фронту. Тексти редагуються в адмінці («Налаштування калькулятора»).
export default function DemoBanner({ show, title, text }: { show: boolean; title: string; text: string }) {
  if (!show) return null;

  return (
    <div
      role="alert"
      data-testid="demo-banner"
      className="bg-warning/15 border border-warning rounded-lg px-4 py-3 flex items-start gap-3 my-4"
    >
      <TriangleAlert className="size-6 shrink-0 text-foreground" strokeWidth={ICON_STROKE} aria-hidden="true" />
      <div className="text-sm text-foreground">
        <p className="font-bold">{title}</p>
        <p className="text-muted-foreground mt-0.5">{text}</p>
      </div>
    </div>
  );
}
