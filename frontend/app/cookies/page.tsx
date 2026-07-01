import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Політика щодо файлів cookie | AUTOforYOU',
  robots: { index: false },
};

export default function CookiesPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <p className="text-xs bg-amber-50 border border-amber-300 text-amber-800 rounded-lg px-4 py-2 mb-8">
        Шаблон — потребує перевірки юристом перед публікацією
      </p>
      <h1 className="text-3xl font-bold text-slate-900 mb-8">Політика щодо файлів cookie</h1>

      <div className="prose prose-slate max-w-none space-y-6 text-slate-700">
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">1. Що таке cookie</h2>
          <p>
            Cookie — це невеликі текстові файли, які зберігаються у вашому браузері під час відвідування
            сайту. Вони допомагають сайту запам&apos;ятовувати ваші налаштування та дії.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">2. Які cookie ми використовуємо</h2>

          <h3 className="font-semibold text-slate-700 mt-4 mb-1">Необхідні (завжди активні)</h3>
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
                <td className="border border-slate-200 px-3 py-2 font-mono">access_token</td>
                <td className="border border-slate-200 px-3 py-2">JWT авторизація</td>
                <td className="border border-slate-200 px-3 py-2">сесія</td>
              </tr>
              <tr>
                <td className="border border-slate-200 px-3 py-2 font-mono">cookie_consent</td>
                <td className="border border-slate-200 px-3 py-2">Запам&apos;ятовує ваш вибір щодо cookie</td>
                <td className="border border-slate-200 px-3 py-2">1 рік</td>
              </tr>
            </tbody>
          </table>

          <h3 className="font-semibold text-slate-700 mt-4 mb-1">Аналітичні (потребують згоди)</h3>
          <p className="text-sm text-slate-500">
            На поточному етапі аналітичні cookie не використовуються. Цей розділ буде оновлено
            після підключення аналітичних сервісів.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">3. Управління cookie</h2>
          <p>
            Ви можете керувати cookie через налаштування вашого браузера або через банер,
            що з&apos;являється при першому відвідуванні сайту. Вимкнення необхідних cookie може
            призвести до некоректної роботи сайту.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">4. Зміни</h2>
          <p>
            Ця Політика може оновлюватися. Актуальна версія завжди доступна на цій сторінці.
          </p>
        </section>

        <p className="text-xs text-slate-400 mt-10 border-t pt-4">
          Останнє оновлення: [дата — заповнити]
        </p>
      </div>
    </div>
  );
}
