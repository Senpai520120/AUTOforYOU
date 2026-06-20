'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { dealersApi } from '@/api/dealers';
import Spinner from '@/components/ui/Spinner';

export default function DealerApplyPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [form, setForm] = useState({
    company_name: '',
    full_name: '',
    contact_phone: '',
    documents: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  if (loading) return <div className="flex justify-center py-20"><Spinner /></div>;

  if (success) {
    return (
      <div className="max-w-md mx-auto text-center py-24">
        <div className="text-5xl mb-4">✅</div>
        <h1 className="text-2xl font-bold text-slate-900 mb-3">Заявку подано!</h1>
        <p className="text-slate-500 mb-6">Менеджер розгляне її та повідомить вас на email.</p>
        <button
          onClick={() => router.push('/me')}
          className="bg-blue-700 text-white px-6 py-2.5 rounded-xl font-semibold hover:bg-blue-800 transition-colors"
        >
          До кабінету
        </button>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await dealersApi.apply({
        company_name: form.company_name,
        full_name: form.full_name,
        contact_phone: form.contact_phone,
        documents: form.documents || undefined,
      });
      setSuccess(true);
    } catch (err: unknown) {
      const detail = (err as { detail?: string })?.detail;
      setError(detail || 'Помилка при поданні заявки. Спробуйте ще раз.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto py-12">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Заявка на B2B-доступ</h1>
      <p className="text-slate-500 mb-8 text-sm">
        Заповніть форму — менеджер розгляне вашу заявку та надасть доступ до оптового каталогу.
      </p>

      <form onSubmit={handleSubmit} className="space-y-5 bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Назва компанії *</label>
          <input
            required
            value={form.company_name}
            onChange={e => setForm(f => ({ ...f, company_name: e.target.value }))}
            placeholder="ТОВ Авто Трейд"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">ПІБ *</label>
          <input
            required
            value={form.full_name}
            onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
            placeholder="Іван Петрович Іванов"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Контактний телефон *</label>
          <input
            required
            type="tel"
            value={form.contact_phone}
            onChange={e => setForm(f => ({ ...f, contact_phone: e.target.value }))}
            placeholder="+380991234567"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Посилання на документи <span className="text-slate-400 font-normal">(необов&#39;язково)</span>
          </label>
          <input
            type="url"
            value={form.documents}
            onChange={e => setForm(f => ({ ...f, documents: e.target.value }))}
            placeholder="https://drive.google.com/..."
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-slate-400 mt-1">Виписка з ЄДР, свідоцтво про реєстрацію або інший документ</p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-amber-500 hover:bg-amber-400 disabled:opacity-60 text-black font-semibold py-2.5 rounded-xl transition-colors"
        >
          {submitting ? 'Відправляємо...' : 'Подати заявку'}
        </button>
      </form>
    </div>
  );
}
