import type { Metadata } from 'next';
import Link from 'next/link';
import CookieSettings from '@/components/ui/CookieSettings';

export const metadata: Metadata = {
  title: 'Політика щодо файлів cookie та сховища браузера | AUTOforYOU',
};

export default function CookiesPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <p className="text-xs bg-amber-50 border border-amber-300 text-amber-800 rounded-lg px-4 py-2 mb-8">
        Шаблон — потребує перевірки юристом перед публікацією
      </p>
      <h1 className="text-3xl font-bold text-slate-900 mb-8">
        Політика щодо файлів cookie та сховища браузера
      </h1>

      <div className="prose prose-slate max-w-none space-y-6 text-slate-700">
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">1. Що ми використовуємо</h2>
          <p>
            Для роботи сайту ми зберігаємо дані у вашому браузері. Основна частина зберігається
            не у файлах cookie, а в <strong>localStorage</strong> — це інша технологія, але з точки
            зору захисту персональних даних до неї застосовуються ті самі вимоги, тому ми розкриваємо
            її нарівні з cookie.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">2. Дані у сховищі браузера</h2>

          <h3 className="font-semibold text-slate-700 mt-4 mb-1">
            Необхідні для роботи сайту (згода не потрібна)
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse border border-slate-200 rounded">
              <thead className="bg-slate-50">
                <tr>
                  <th className="border border-slate-200 px-3 py-2 text-left">Ключ</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Технологія</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Мета</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Термін</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">access</td>
                  <td className="border border-slate-200 px-3 py-2">localStorage</td>
                  <td className="border border-slate-200 px-3 py-2">Токен доступу до акаунта</td>
                  <td className="border border-slate-200 px-3 py-2">15 хвилин</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">refresh</td>
                  <td className="border border-slate-200 px-3 py-2">localStorage</td>
                  <td className="border border-slate-200 px-3 py-2">Продовження сесії без повторного входу</td>
                  <td className="border border-slate-200 px-3 py-2">7 днів</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">cookie_consent</td>
                  <td className="border border-slate-200 px-3 py-2">localStorage</td>
                  <td className="border border-slate-200 px-3 py-2">Запам&apos;ятовує ваш вибір на цій сторінці</td>
                  <td className="border border-slate-200 px-3 py-2">до очищення браузера</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-sm text-slate-500 mt-2">
            Значення <span className="font-mono">access</span> і <span className="font-mono">refresh</span>{' '}
            видаляються під час виходу з акаунта.
          </p>

          <h3 className="font-semibold text-slate-700 mt-6 mb-1">
            Cookie адміністративної панелі
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse border border-slate-200 rounded">
              <thead className="bg-slate-50">
                <tr>
                  <th className="border border-slate-200 px-3 py-2 text-left">Назва</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Мета</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Термін</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">sessionid</td>
                  <td className="border border-slate-200 px-3 py-2">Сесія адміністратора</td>
                  <td className="border border-slate-200 px-3 py-2">2 тижні</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">csrftoken</td>
                  <td className="border border-slate-200 px-3 py-2">Захист форм адмінпанелі від CSRF</td>
                  <td className="border border-slate-200 px-3 py-2">1 рік</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-sm text-slate-500 mt-2">
            Ці cookie встановлюються лише при відвідуванні <span className="font-mono">/admin</span>{' '}
            і не стосуються звичайних користувачів сайту.
          </p>

          <h3 className="font-semibold text-slate-700 mt-6 mb-1">
            Аналітичні та рекламні (потребують згоди)
          </h3>
          <p className="text-sm">
            <strong>Наразі не використовуються.</strong> На сайті немає систем веб-аналітики,
            рекламних пікселів і сторонніх скриптів відстеження. Якщо ми їх підключимо, вони
            запрацюють лише після того, як ви оберете «Прийняти всі» — до цього моменту вони
            заблоковані на рівні коду.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">3. Сторонні сервіси</h2>
          <p>Сайт звертається до зовнішніх сервісів лише в таких випадках:</p>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>
              <strong>Telegram</strong> — якщо ви самостійно прив&apos;язали акаунт. Передається
              лише ваш <span className="font-mono">telegram_id</span>.
            </li>
            <li>
              <strong>LiqPay</strong> — при оплаті платних послуг просування оголошень. Платіжні
              дані вводяться на стороні LiqPay, ми їх не отримуємо і не зберігаємо.
            </li>
            <li>
              <strong>Зображення</strong> — фото оголошень можуть завантажуватися з зовнішніх
              сховищ. При цьому ваш браузер звертається до цих сховищ напряму.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">4. Ваш вибір</h2>
          <p className="mb-4">
            Ви можете змінити або відкликати згоду будь-коли. Вимкнення необхідних даних
            неможливе — без них не працює вхід в акаунт.
          </p>
          <CookieSettings />
          <p className="mt-4 text-sm">
            Очистити сховище повністю можна також через налаштування вашого браузера.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">5. Зміни</h2>
          <p>
            Ця Політика може оновлюватися. Актуальна версія завжди доступна на цій сторінці.
            Дивіться також{' '}
            <Link href="/privacy" className="text-blue-600 hover:underline">
              Політику конфіденційності
            </Link>
            .
          </p>
        </section>

        <p className="text-xs text-slate-400 mt-10 border-t pt-4">
          Останнє оновлення: [дата — заповнити]
        </p>
      </div>
    </div>
  );
}
