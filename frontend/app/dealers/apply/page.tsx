'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useRequireAuth } from '@/lib/use-require-auth';
import { dealersApi } from '@/api/dealers';
import Spinner from '@/components/ui/Spinner';
import Captcha from '@/components/ui/Captcha';
import EmailNotVerified from '@/components/ui/EmailNotVerified';
import { apiErrorText, useAuthConfig, useCaptchaState } from '@/lib/captcha';
import { AGE_18_LABEL, AGE_18_REQUIRED } from '@/lib/labels';
import { isEmailNotVerified } from '@/lib/email-verify';

export default function DealerApplyPage() {
  const { loading } = useRequireAuth();
  const router = useRouter();

  const [form, setForm] = useState({
    company_name: '',
    full_name: '',
    contact_phone: '',
    documents: '',
  });
  const [agreedToProcessing, setAgreedToProcessing] = useState(false);
  const [confirmedAge18, setConfirmedAge18] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [notVerified, setNotVerified] = useState(false);
  const { config } = useAuthConfig();
  const captcha = useCaptchaState();

  if (loading) return <div className="flex justify-center py-20"><Spinner /></div>;

  if (success) {
    return (
      <div className="max-w-md mx-auto text-center py-24">
        <div className="text-5xl mb-4">✅</div>
        <h1 className="text-2xl font-bold text-foreground mb-3">Заявку подано!</h1>
        <p className="text-muted-foreground mb-6">Менеджер розгляне її та повідомить вас на email.</p>
        <button
          onClick={() => router.push('/me')}
          className="bg-primary text-primary-foreground px-6 py-2.5 rounded-xl font-semibold hover:bg-primary/90 transition-colors"
        >
          До кабінету
        </button>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agreedToProcessing) {
      setError('Для подання заявки потрібна згода на обробку персональних даних.');
      return;
    }
    if (!confirmedAge18) {
      setError(AGE_18_REQUIRED);
      return;
    }
    setError(null);
    setNotVerified(false);
    setSubmitting(true);
    try {
      await dealersApi.apply({
        company_name: form.company_name,
        full_name: form.full_name,
        contact_phone: form.contact_phone,
        documents: form.documents || undefined,
        agreed_to_processing: agreedToProcessing,
        confirmed_age_18: confirmedAge18,
        ...captcha.payload(),
      });
      setSuccess(true);
    } catch (err: unknown) {
      if (isEmailNotVerified(err)) setNotVerified(true);
      else setError(apiErrorText(err, 'Помилка при поданні заявки. Спробуйте ще раз.'));
    } finally {
      setSubmitting(false);
      captcha.bump(); // токен одноразовий: новий після кожної відповіді сервера
    }
  };

  return (
    <div className="max-w-lg mx-auto py-12">
      <h1 className="text-2xl font-bold text-foreground mb-2">Заявка на B2B-доступ</h1>
      <p className="text-muted-foreground mb-8 text-sm">
        Заповніть форму — менеджер розгляне вашу заявку та надасть доступ до оптового каталогу.
      </p>

      <form onSubmit={handleSubmit} className="space-y-5 bg-card rounded-2xl shadow-sm border border-border p-6">
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">Назва компанії *</label>
          <input
            required
            value={form.company_name}
            onChange={e => setForm(f => ({ ...f, company_name: e.target.value }))}
            placeholder="ТОВ Авто Трейд"
            className="w-full border border-input rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-foreground mb-1">ПІБ *</label>
          <input
            required
            value={form.full_name}
            onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
            placeholder="Іван Петрович Іванов"
            className="w-full border border-input rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-foreground mb-1">Контактний телефон *</label>
          <input
            required
            type="tel"
            value={form.contact_phone}
            onChange={e => setForm(f => ({ ...f, contact_phone: e.target.value }))}
            placeholder="+380991234567"
            className="w-full border border-input rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            Посилання на документи <span className="text-muted-foreground font-normal">(необов&#39;язково)</span>
          </label>
          <input
            type="url"
            value={form.documents}
            onChange={e => setForm(f => ({ ...f, documents: e.target.value }))}
            placeholder="https://drive.google.com/..."
            className="w-full border border-input rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <p className="text-xs text-muted-foreground mt-1">Виписка з ЄДР, свідоцтво про реєстрацію або інший документ</p>
        </div>

        <div className="flex items-start gap-3 pt-1">
          <input
            id="agreed_to_processing"
            type="checkbox"
            checked={agreedToProcessing}
            onChange={e => setAgreedToProcessing(e.target.checked)}
            className="mt-1 h-4 w-4 shrink-0 rounded border-input text-primary focus:ring-2 focus:ring-ring"
          />
          <label htmlFor="agreed_to_processing" className="text-sm text-muted-foreground">
            Я даю згоду на обробку вказаних персональних даних (ПІБ, телефон, документи компанії)
            з метою розгляду цієї заявки, відповідно до{' '}
            <Link href="/privacy" className="text-link hover:underline" target="_blank">
              Політики конфіденційності
            </Link>
            .
          </label>
        </div>

        <div className="flex items-start gap-3">
          <input
            id="confirmed_age_18"
            type="checkbox"
            checked={confirmedAge18}
            onChange={e => setConfirmedAge18(e.target.checked)}
            className="mt-1 h-4 w-4 shrink-0 rounded border-input text-primary focus:ring-2 focus:ring-ring"
          />
          <label htmlFor="confirmed_age_18" className="text-sm text-muted-foreground">
            {AGE_18_LABEL}
          </label>
        </div>

        <Captcha config={config?.captcha ?? null} onToken={captcha.setToken}
          resetKey={captcha.resetKey} onHoneypot={captcha.setWebsite} />

        {notVerified && <EmailNotVerified />}
        {error && (
          <div className="bg-destructive/10 border border-destructive/40 text-destructive rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !captcha.ready}
          className="w-full bg-accent hover:bg-accent/90 disabled:opacity-60 text-accent-foreground font-semibold py-2.5 rounded-xl transition-colors"
        >
          {submitting ? 'Відправляємо...' : 'Подати заявку'}
        </button>
      </form>
    </div>
  );
}
