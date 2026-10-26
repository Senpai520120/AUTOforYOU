import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import Link from 'next/link';
import CookieSettings from '@/components/ui/CookieSettings';
import LegalPage from '@/components/legal/LegalPage';
import { getSiteSettings } from '@/lib/site-settings';

export const metadata: Metadata = buildMetadata({
  title: 'Політика щодо файлів cookie та сховища браузера',
  description:
    'Які cookie та дані браузера використовує AUTOforYOU, навіщо вони потрібні та як керувати згодою.',
  path: '/cookies',
});

export const dynamic = 'force-dynamic';

export default async function CookiesPage() {
  const s = await getSiteSettings(0);
  return (
    <LegalPage title="Політика щодо файлів cookie та сховища браузера" settings={s}>
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">1. Що ми використовуємо</h2>
          <p>
            Для входу в акаунт сайт використовує <strong>файли cookie</strong> з позначкою 
            <strong>HttpOnly</strong>: їх читає лише наш сервер, скрипти на сторінці доступу до них
            не мають. Окремо в сховищі браузера (<strong>localStorage</strong>) зберігається тільки
            ваш вибір щодо cookie. З точки зору захисту персональних даних до обох технологій
            застосовуються ті самі вимоги, тому ми розкриваємо їх разом.
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
                  <th className="border border-slate-200 px-3 py-2 text-left">Назва</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Технологія</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Мета</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Термін</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">access</td>
                  <td className="border border-slate-200 px-3 py-2">cookie, HttpOnly</td>
                  <td className="border border-slate-200 px-3 py-2">Токен доступу до акаунта</td>
                  <td className="border border-slate-200 px-3 py-2">15 хвилин (налаштовується)</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">refresh</td>
                  <td className="border border-slate-200 px-3 py-2">cookie, HttpOnly</td>
                  <td className="border border-slate-200 px-3 py-2">Продовження сесії без повторного входу. Надсилається лише на адреси входу й виходу</td>
                  <td className="border border-slate-200 px-3 py-2">7 днів (налаштовується)</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">has_session</td>
                  <td className="border border-slate-200 px-3 py-2">cookie</td>
                  <td className="border border-slate-200 px-3 py-2">Позначка «ви увійшли» без токена — щоб не робити зайвих запитів, коли ви не в акаунті</td>
                  <td className="border border-slate-200 px-3 py-2">7 днів (налаштовується)</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2 font-mono">csrftoken</td>
                  <td className="border border-slate-200 px-3 py-2">cookie</td>
                  <td className="border border-slate-200 px-3 py-2">Захист від підроблених запитів (CSRF) від імені вашого акаунта</td>
                  <td className="border border-slate-200 px-3 py-2">1 рік</td>
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
            Cookie <span className="font-mono">access</span> і <span className="font-mono">refresh</span> 
            видаляються під час виходу з акаунта, а сесія скасовується на сервері.
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
              </tbody>
            </table>
          </div>
          <p className="text-sm text-slate-500 mt-2">
            Cookie <span className="font-mono">sessionid</span> встановлюється лише при відвідуванні{' '}
            <span className="font-mono">/admin</span> і не стосується звичайних користувачів сайту.
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

    </LegalPage>
  );
}
