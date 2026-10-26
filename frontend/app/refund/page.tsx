import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import Link from 'next/link';
import LegalPage, { EmailOrMissing } from '@/components/legal/LegalPage';
import { getSiteSettings, supportContact } from '@/lib/site-settings';
import { serverGet } from '@/lib/server-api';
import type { PromotionTariff } from '@/lib/types';

export const metadata: Metadata = buildMetadata({
  title: 'Політика повернення коштів',
  description:
    'Політика повернення коштів за платні послуги просування оголошень на AUTOforYOU.',
  path: '/refund',
});

export const dynamic = 'force-dynamic';

export default async function RefundPage() {
  const s = await getSiteSettings(0);
  const tariffs = s?.payments_enabled === true
    ? (await serverGet<PromotionTariff[]>('/api/v1/local/tariffs/', 0)) ?? []
    : [];
  return (
    <LegalPage title="Політика повернення коштів" settings={s}>
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-2">1. Які послуги є платними</h2>
          {/* 6.4 (11-C8, Q9): таблиця — з GET /api/v1/local/tariffs/; при PAYMENTS_ENABLED=false — без неї */}
          {s?.payments_enabled !== true ? (
            <p data-testid="refund-payments-off">
              Реєстрація, подання оголошень, пошук і калькулятор — безкоштовні. Платні послуги наразі недоступні,
              розміщення та продовження оголошень безкоштовні.
            </p>
          ) : tariffs.length === 0 ? (
            <p data-testid="refund-no-tariffs">Платних послуг наразі немає.</p>
          ) : (
            <>
              <p>
                Реєстрація, подання оголошень, пошук і калькулятор — безкоштовні. Платними є лише
                послуги просування власних оголошень:
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse border border-slate-200 rounded" data-testid="refund-tariffs">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="border border-slate-200 px-3 py-2 text-left">Послуга</th>
                      <th className="border border-slate-200 px-3 py-2 text-left">Що дає</th>
                      <th className="border border-slate-200 px-3 py-2 text-left">Строк</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tariffs.map((t) => (
                      <tr key={t.id}>
                        <td className="border border-slate-200 px-3 py-2">{t.name}</td>
                        <td className="border border-slate-200 px-3 py-2">{t.description}</td>
                        <td className="border border-slate-200 px-3 py-2">
                          {t.duration_days > 0 ? `${t.duration_days} днів` : 'одноразово'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {s?.payments_enabled === true && (
            <p className="text-sm text-slate-500 mt-2">
              Актуальні ціни вказані на сторінці оголошення в момент замовлення послуги.
              Оплата приймається через платіжний сервіс LiqPay.
            </p>
          )}
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
            <EmailOrMissing email={supportContact(s)} />
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

    </LegalPage>
  );
}
