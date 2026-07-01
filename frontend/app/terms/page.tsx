import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Умови використання | AUTOforYOU',
  robots: { index: false },
};

export default function TermsPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <p className="text-xs bg-amber-50 border border-amber-300 text-amber-800 rounded-lg px-4 py-2 mb-8">
        Шаблон — потребує перевірки юристом перед публікацією
      </p>
      <h1 className="text-3xl font-bold text-slate-900 mb-8">Умови використання</h1>

      <div className="prose prose-slate max-w-none space-y-6 text-slate-700">
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">1. Загальні положення</h2>
          <p>
            Ці Умови використання (далі — «Умови») регулюють відносини між сервісом AUTOforYOU
            (далі — «Платформа», «ми») та користувачами (далі — «ви», «користувач»).
            Використовуючи Платформу, ви підтверджуєте, що ознайомилися з цими Умовами та погоджуєтеся
            з ними в повному обсязі.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">2. Послуги Платформи</h2>
          <p>
            AUTOforYOU — маркетплейс транспортних засобів з аукціонів США (Copart, IAAI) з доставкою
            в Україну. Ми надаємо інформацію про автомобілі, розраховуємо орієнтовну вартість
            розмитнення та допомагаємо з пошуком транспортних засобів.
          </p>
          <p className="text-sm text-slate-500">
            Усі розрахунки є орієнтовними (is_estimate: true) та не є офіційною консультацією.
            Актуальні митні ставки необхідно уточнювати на офіційних ресурсах Митної служби України.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">3. Реєстрація та обліковий запис</h2>
          <p>
            Для доступу до частини функцій необхідна реєстрація. Ви зобов&apos;язані надати достовірні
            дані та зберігати конфіденційність свого пароля. Платформа не несе відповідальності за
            наслідки несанкціонованого доступу до вашого облікового запису.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">4. Права та обов&apos;язки користувача</h2>
          <p>Ви зобов&apos;язані:</p>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>використовувати Платформу лише в законних цілях;</li>
            <li>не розміщувати недостовірну або шкідливу інформацію;</li>
            <li>не порушувати права третіх осіб.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">5. Відповідальність</h2>
          <p>
            Платформа надає інформацію «як є». Ми не гарантуємо безперервну роботу сервісу та не несемо
            відповідальності за збитки, що виникли внаслідок використання Платформи або неможливості
            її використання.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">6. Зміни Умов</h2>
          <p>
            Ми залишаємо за собою право змінювати ці Умови. Про суттєві зміни ми повідомлятимемо
            електронною поштою або через сповіщення на Платформі. Продовження використання Платформи
            після публікації змін означає вашу згоду з новими Умовами.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">7. Контакти</h2>
          <p>
            З питань щодо цих Умов звертайтеся за адресою:{' '}
            <span className="font-mono text-slate-600">[email@autoforyou.ua — заповнити]</span>
          </p>
        </section>

        <p className="text-xs text-slate-400 mt-10 border-t pt-4">
          Останнє оновлення: [дата — заповнити]
        </p>
      </div>
    </div>
  );
}
