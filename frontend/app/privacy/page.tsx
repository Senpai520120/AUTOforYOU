import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Політика конфіденційності | AUTOforYOU',
  robots: { index: false },
};

export default function PrivacyPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <p className="text-xs bg-amber-50 border border-amber-300 text-amber-800 rounded-lg px-4 py-2 mb-8">
        Шаблон — потребує перевірки юристом перед публікацією
      </p>
      <h1 className="text-3xl font-bold text-slate-900 mb-8">Політика конфіденційності</h1>

      <div className="prose prose-slate max-w-none space-y-6 text-slate-700">
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">1. Хто ми</h2>
          <p>
            AUTOforYOU — маркетплейс транспортних засобів. Ця Політика пояснює, які персональні дані
            ми збираємо, як ми їх використовуємо та захищаємо.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">2. Дані, які ми збираємо</h2>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li><strong>Дані облікового запису:</strong> email, ім&apos;я, номер телефону, роль.</li>
            <li><strong>Дані активності:</strong> переглянуті оголошення, запити до калькулятора.</li>
            <li><strong>Технічні дані:</strong> IP-адреса, тип браузера, cookie-файли.</li>
            <li><strong>Дата згоди з Умовами</strong> (зберігається разом з обліковим записом).</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">3. Мета обробки</h2>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>надання послуг Платформи та підтримка облікового запису;</li>
            <li>надсилання сповіщень про статус доставки (якщо підключено Telegram);</li>
            <li>покращення якості сервісу;</li>
            <li>дотримання вимог законодавства.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">4. Правова підстава</h2>
          <p>
            Обробка ваших даних здійснюється на підставі вашої згоди (ст. 11 Закону України
            «Про захист персональних даних»), а також виконання договору та законних інтересів
            Платформи.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">5. Передача даних третім особам</h2>
          <p>
            Ми не продаємо ваші персональні дані. Дані можуть передаватися:
          </p>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>хостинг-провайдерам для роботи інфраструктури;</li>
            <li>Telegram (при використанні бота, лише telegram_id);</li>
            <li>державним органам на законну вимогу.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">6. Ваші права</h2>
          <p>Ви маєте право:</p>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>отримати копію своїх даних;</li>
            <li>виправити неточні дані;</li>
            <li>видалити обліковий запис;</li>
            <li>відкликати згоду на обробку.</li>
          </ul>
          <p className="mt-2">
            Запити направляйте на:{' '}
            <span className="font-mono text-slate-600">[privacy@autoforyou.ua — заповнити]</span>
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">7. Зберігання та безпека</h2>
          <p>
            Дані зберігаються на захищених серверах. Паролі зберігаються в захешованому вигляді.
            Термін зберігання — протягом дії облікового запису та [X] років після його видалення.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">8. Cookie</h2>
          <p>
            Детальніше про використання cookie дивіться у нашій{' '}
            <a href="/cookies" className="text-blue-600 hover:underline">Політиці щодо файлів cookie</a>.
          </p>
        </section>

        <p className="text-xs text-slate-400 mt-10 border-t pt-4">
          Останнє оновлення: [дата — заповнити]
        </p>
      </div>
    </div>
  );
}
