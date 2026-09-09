import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="bg-slate-900 text-slate-400 mt-auto py-8">
      <div className="max-w-7xl mx-auto px-4 text-center text-sm">
        <p className="font-semibold text-white mb-1">AUTOforYOU — маркетплейс авто з США</p>
        <p>Copart · IAAI · доставка під ключ в Україну</p>
        <nav aria-label="Юридичні документи" className="mt-4 flex justify-center gap-5 text-xs text-slate-500 flex-wrap">
          <Link href="/terms" className="hover:text-slate-300 transition-colors">Умови використання</Link>
          <Link href="/rules" className="hover:text-slate-300 transition-colors">Правила розміщення</Link>
          <Link href="/refund" className="hover:text-slate-300 transition-colors">Повернення коштів</Link>
          <Link href="/privacy" className="hover:text-slate-300 transition-colors">Конфіденційність</Link>
          <Link href="/cookies" className="hover:text-slate-300 transition-colors">Cookie</Link>
        </nav>
        <p className="mt-3 text-xs text-slate-500">
          Тестові тарифи — всі розрахунки є демонстраційними
        </p>
      </div>
    </footer>
  );
}
