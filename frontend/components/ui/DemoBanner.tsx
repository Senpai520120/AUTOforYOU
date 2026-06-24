// Демо-баннер управляется флагом NEXT_PUBLIC_DEMO_MODE.
// При NEXT_PUBLIC_DEMO_MODE=false баннер скрывается — включить на проде с реальными тарифами.
// Дисклеймер is_estimate в ответе API всегда присутствует независимо от этого флага.
const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE !== 'false';

export default function DemoBanner({ text }: { text?: string }) {
  if (!isDemoMode) return null;

  return (
    <div
      role="alert"
      className="bg-amber-50 border border-amber-400 rounded-lg px-4 py-3 flex items-start gap-3 my-4"
    >
      <span className="text-2xl leading-none" aria-hidden="true">⚠</span>
      <div className="text-sm text-amber-900">
        <p className="font-bold">Тестові тарифи — розрахунок демонстраційний</p>
        <p className="text-amber-800 mt-0.5">
          {text ?? 'Ставки акцизу, мита та фрахту є плейсхолдерами. Не використовуйте ці цифри для реальних угод.'}
        </p>
      </div>
    </div>
  );
}
