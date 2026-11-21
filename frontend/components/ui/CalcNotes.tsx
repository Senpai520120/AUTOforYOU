// 9.51: «ставки станом на <дата>» і «що не входить» — спільні для калькулятора й сторінок «Пригон ... з США».
// Лише відображення: дата, ознака давності й пункти приходять з API (тексти правляться в адмінці).

export function formatNoteDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return y && m && d ? `${d}.${m}.${y}` : iso;
}

interface FeesProps {
  checkedOn?: string | null;
  stale?: boolean;
}

/** Дата звірки аукціонних ставок із сайтом аукціону; червона позначка, якщо звірці понад 90 днів. */
export function FeesFreshness({ checkedOn, stale }: FeesProps) {
  if (!checkedOn) return null;
  if (stale) {
    return (
      <p data-testid="fees-stale" role="status"
        className="text-xs text-destructive bg-destructive/10 border border-destructive/30 rounded-md p-2 mt-2">
        Аукціонні збори звірено з сайтом аукціону {formatNoteDate(checkedOn)} — понад 90 днів тому. Фактичні ставки
        могли змінитися: вартість підтвердить брокер.
      </p>
    );
  }
  return (
    <p data-testid="fees-checked" className="text-xs text-muted-foreground mt-2">
      Ставки аукціонних зборів станом на {formatNoteDate(checkedOn)}.
    </p>
  );
}

/** Що не входить у розрахунок (ремонт, сертифікація, доставка по Україні, комісія брокера). */
export function ExclusionsList({ items }: { items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="mt-4" data-testid="calc-exclusions">
      <h3 className="font-semibold text-foreground text-sm">Що не входить у розрахунок</h3>
      <ul className="list-disc pl-5 mt-1 text-sm text-muted-foreground">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
