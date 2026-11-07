// Демо-банер (2.6): показується за is_demo з API — коли всі тарифи позначені перевіреними, зникає сам,
// без перебудови фронту. Тексти редагуються в адмінці («Налаштування калькулятора»).
export default function DemoBanner({ show, title, text }: { show: boolean; title: string; text: string }) {
  if (!show) return null;

  return (
    <div
      role="alert"
      data-testid="demo-banner"
      className="bg-amber-50 border border-amber-400 rounded-lg px-4 py-3 flex items-start gap-3 my-4"
    >
      <span className="text-2xl leading-none" aria-hidden="true">⚠</span>
      <div className="text-sm text-amber-900">
        <p className="font-bold">{title}</p>
        <p className="text-amber-800 mt-0.5">{text}</p>
      </div>
    </div>
  );
}
