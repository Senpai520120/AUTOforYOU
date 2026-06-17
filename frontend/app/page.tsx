import Link from 'next/link';

export default function Home() {
  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-br from-blue-900 to-blue-700 text-white rounded-2xl p-12 mb-10 text-center">
        <h1 className="text-4xl font-extrabold mb-3">Авто з США під ключ в Україну</h1>
        <p className="text-blue-200 text-lg mb-8 max-w-xl mx-auto">
          Copart · IAAI · доставка · розмитнення · калькулятор вартості
        </p>
        <div className="flex flex-wrap gap-4 justify-center">
          <Link
            href="/listings"
            className="bg-amber-400 hover:bg-amber-300 text-black font-bold px-8 py-3 rounded-xl text-lg transition-colors"
          >
            Переглянути каталог
          </Link>
          <Link
            href="/calculator"
            className="bg-white/10 hover:bg-white/20 border border-white/30 text-white font-semibold px-8 py-3 rounded-xl text-lg transition-colors"
          >
            Калькулятор
          </Link>
        </div>
        <p className="mt-6 text-xs text-amber-300">
          ⚠ Тестові тарифи — всі розрахунки є демонстраційними
        </p>
      </section>

      {/* Features */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        {[
          { icon: '🚗', title: 'Каталог авто', desc: 'Всі статуси: в дорозі, є в наявності, продано', href: '/listings' },
          { icon: '🧮', title: 'Калькулятор', desc: 'Повна розбивка: аукціон, логістика, розмитнення', href: '/calculator' },
          { icon: '📦', title: 'Трекінг', desc: 'Відстежуйте контейнери від складу до вашого гаража', href: '/me/shipments' },
        ].map(f => (
          <Link key={f.href} href={f.href} className="bg-white border border-slate-200 rounded-xl p-6 hover:shadow-md hover:border-blue-300 transition-all group">
            <div className="text-4xl mb-3">{f.icon}</div>
            <h3 className="font-bold text-slate-900 group-hover:text-blue-700 transition-colors mb-1">{f.title}</h3>
            <p className="text-sm text-slate-500">{f.desc}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
