import type { Metadata } from 'next';
import LegalPage, { EmailOrMissing } from '@/components/legal/LegalPage';
import { getSiteSettings, supportContact } from '@/lib/site-settings';

export const metadata: Metadata = {
  title: 'Умови використання | AUTOforYOU',
};

export const dynamic = 'force-dynamic';

export default async function TermsPage() {
  const s = await getSiteSettings(0);
  return (
    <LegalPage title="Умови використання" settings={s}>
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
          <p>
            Послугу пригону автомобіля надає партнер, а не AUTOforYOU.
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
            <EmailOrMissing email={supportContact(s)} />
          </p>
        </section>

    </LegalPage>
  );
}
