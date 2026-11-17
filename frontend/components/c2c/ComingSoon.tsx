import Link from 'next/link';

/** Заглушка закритого розділу. section — C2C вимкнено; posting — «засів», подача ще закрита. */
export default function ComingSoon({ variant = 'section' }: { variant?: 'section' | 'posting' }) {
  const posting = variant === 'posting';
  return (
    <div className="max-w-xl mx-auto text-center py-16" data-testid="c2c-coming-soon">
      <div className="text-5xl mb-4" aria-hidden="true">🚧</div>
      <h1 className="text-2xl font-bold text-slate-900 mb-2">
        {posting ? 'Подача оголошень скоро відкриється' : 'Оголошення по Україні — незабаром'}
      </h1>
      <p className="text-slate-500 mb-6">
        {posting
          ? 'Зараз оголошення додає команда сайту. Перегляньте каталог.'
          : 'Розділ ще готується до запуску. Тим часом порахуйте вартість авто з США.'}
      </p>
      <Link
        href={posting ? '/ua' : '/calculator'}
        className="inline-block bg-blue-700 hover:bg-blue-800 text-white font-semibold px-6 py-2.5 rounded-xl transition-colors"
      >
        {posting ? 'Перейти до каталогу' : 'Перейти до калькулятора'}
      </Link>
    </div>
  );
}
