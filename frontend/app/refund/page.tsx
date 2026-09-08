import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Політика повернення коштів | AUTOforYOU',
};

export default function RefundPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <p className="text-xs bg-amber-50 border border-amber-300 text-amber-800 rounded-lg px-4 py-2 mb-8">
        Шаблон — потребує перевірки юристом перед публікацією
      </p>
      <h1 className="text-3xl font-bold text-slate-900 mb-8">Політика повернення коштів</h1>

      <div className="prose prose-slate max-w-none space-y-6 text-slate-700">
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">1. Які послуги є платними</h2>
          <p>
            Реєстрація, подання оголошень, пошук і калькулятор — безкоштовні. Платними є лише
            послуги просування власних оголошень:
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse border border-slate-200 rounded">
              <thead className="bg-slate-50">
                <tr>
                  <th className="border border-slate-200 px-3 py-2 text-left">Послуга</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Що дає</th>
                  <th className="border border-slate-200 px-3 py-2 text-left">Строк</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="border border-slate-200 px-3 py-2">Продовження на 30 днів</td>
                  <td className="border border-slate-200 px-3 py-2">Подовжує термін дії оголошення</td>
                  <td className="border border-slate-200 px-3 py-2">30 днів</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2">Підняти в топ списку</td>
                  <td className="border border-slate-200 px-3 py-2">Одноразове підняття вгору списку</td>
                  <td className="border border-slate-200 px-3 py-2">одноразово</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2">ТОП 7 днів</td>
                  <td className="border border-slate-200 px-3 py-2">Закріплення у ТОП-блоці каталогу</td>
                  <td className="border border-slate-200 px-3 py-2">7 днів</td>
                </tr>
                <tr>
                  <td className="border border-slate-200 px-3 py-2">ТОП 30 днів</td>
                  <td className="border border-slate-200 px-3 py-2">Закріплення у ТОП-блоці каталогу</td>
                  <td className="border border-slate-200 px-3 py-2">30 днів</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-sm text-slate-500 mt-2">
            Актуальні ціни вказані на сторінці оголошення в момент замовлення послуги.
            Оплата приймається через платіжний сервіс LiqPay.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">2. Право на відмову</h2>
          <p>
            Згідно зі ст. 13 Закону України «Про захист прав споживачів» ви маєте право
            відмовитися від замовленої дистанційно послуги протягом <strong>14 днів</strong>.
          </p>
          <p>
            Зверніть увагу: послуги просування починають надаватися одразу після успішної
            оплати. Замовляючи їх, ви даєте згоду на негайний початок надання послуги —
            після цього право на відмову втрачається в частині вже наданої послуги.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">3. Коли ми повертаємо кошти</h2>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>послуга не була надана через технічну помилку на нашому боці;</li>
            <li>кошти списано двічі за одне замовлення;</li>
            <li>
              оголошення знято Платформою до закінчення оплаченого періоду не з вашої вини —
              повертається вартість ненаданої частини послуги;
            </li>
            <li>ви відмовилися від послуги до моменту її фактичного початку.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">4. Коли кошти не повертаються</h2>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>послуга надана в повному обсязі;</li>
            <li>
              оголошення знято за порушення{' '}
              <Link href="/rules" className="text-blue-600 hover:underline">
                Правил розміщення
              </Link>{' '}
              або внаслідок блокування вашого акаунта;
            </li>
            <li>
              просування не принесло очікуваного результату — ми не гарантуємо продаж
              транспортного засобу чи певну кількість переглядів.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">5. Як подати запит</h2>
          <p>Надішліть запит із зазначенням:</p>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>email, на який зареєстровано акаунт;</li>
            <li>номер замовлення (order_id) або дату та суму платежу;</li>
            <li>причину звернення.</li>
          </ul>
          <p className="mt-2">
            Адреса для звернень:{' '}
            <span className="font-mono text-slate-600">[email — заповнити]</span>
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">6. Строки</h2>
          <p>
            Ми розглядаємо запит протягом <strong>14 календарних днів</strong> з моменту отримання.
            У разі позитивного рішення кошти повертаються тим самим способом, яким було здійснено
            оплату. Строк зарахування залежить від вашого банку та платіжного сервісу і зазвичай
            становить до 30 днів.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">7. Спори</h2>
          <p>
            Ми прагнемо вирішувати спори шляхом переговорів. Якщо домовитися не вдалося, спір
            вирішується в порядку, передбаченому законодавством України. Ви також можете
            звернутися до Держпродспоживслужби.
          </p>
        </section>

        <p className="text-xs text-slate-400 mt-10 border-t pt-4">
          Останнє оновлення: [дата — заповнити]
        </p>
      </div>
    </div>
  );
}
