'use client';
import { useState } from 'react';
import Link from 'next/link';
import { ApiError } from '@/api/client';
import { meApi } from '@/api/me';
import { useRequireAuth } from '@/lib/use-require-auth';
import type { User } from '@/lib/types';

type FieldErrors = Partial<Record<'first_name' | 'last_name' | 'phone', string>>;

const PHONE_RE = /^\+380\d{9}$/;

function fieldErrors(err: unknown): FieldErrors | null {
  if (!(err instanceof ApiError) || err.status !== 400) return null;
  const data = err.data as Record<string, unknown> | null;
  if (!data || typeof data !== 'object') return null;
  const out: FieldErrors = {};
  for (const key of ['first_name', 'last_name', 'phone'] as const) {
    const value = data[key];
    if (Array.isArray(value) && value.length) out[key] = String(value[0]);
  }
  return Object.keys(out).length ? out : null;
}

export default function ProfilePage() {
  const { user, loading, refreshUser } = useRequireAuth();
  if (loading || !user) return null;
  return <ProfileForm user={user} onSaved={refreshUser} />;
}

function ProfileForm({ user, onSaved }: { user: User; onSaved: () => Promise<void> }) {
  const [firstName, setFirstName] = useState(user.first_name);
  const [lastName, setLastName] = useState(user.last_name);
  const [phone, setPhone] = useState(user.phone);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({}); setError(''); setSaved(false);
    const value = phone.trim();
    if (value && !PHONE_RE.test(value)) {
      setErrors({ phone: 'Телефон у форматі +380XXXXXXXXX.' });
      return;
    }
    setSaving(true);
    try {
      await meApi.profile.update({ first_name: firstName.trim(), last_name: lastName.trim(), phone: value });
      setSaved(true);
      await onSaved();
    } catch (err) {
      const fields = fieldErrors(err);
      if (fields) setErrors(fields);
      else if (err instanceof ApiError && err.status === 429) setError('Забагато запитів. Спробуйте пізніше.');
      else setError('Не вдалося зберегти. Спробуйте пізніше.');
    } finally {
      setSaving(false);
    }
  };

  const input = 'w-full border border-slate-300 rounded-lg px-3 py-2';
  const fieldError = (key: keyof FieldErrors) => errors[key] && (
    <p id={`${key}-error`} role="alert" className="text-red-600 text-sm mt-1">{errors[key]}</p>
  );
  return (
    <div className="max-w-2xl mx-auto">
      <Link href="/me" className="text-sm text-blue-600 hover:underline">← До кабінету</Link>
      <h1 className="text-2xl font-bold text-slate-900 mt-2 mb-6">Профіль</h1>

      <section className="bg-white border border-slate-200 rounded-2xl p-6">
        <p className="text-sm text-slate-500 mb-4">
          Email: <span className="font-semibold text-slate-700">{user.email}</span> (змінити email не можна)
        </p>
        <form onSubmit={submit} noValidate className="space-y-4">
          <div>
            <label htmlFor="first-name" className="block text-sm font-semibold text-slate-700 mb-1">Ім&apos;я</label>
            <input id="first-name" maxLength={150} autoComplete="given-name" className={input}
              aria-invalid={!!errors.first_name} aria-describedby={errors.first_name ? 'first_name-error' : undefined}
              value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            {fieldError('first_name')}
          </div>
          <div>
            <label htmlFor="last-name" className="block text-sm font-semibold text-slate-700 mb-1">Прізвище</label>
            <input id="last-name" maxLength={150} autoComplete="family-name" className={input}
              aria-invalid={!!errors.last_name} aria-describedby={errors.last_name ? 'last_name-error' : undefined}
              value={lastName} onChange={(e) => setLastName(e.target.value)} />
            {fieldError('last_name')}
          </div>
          <div>
            <label htmlFor="phone" className="block text-sm font-semibold text-slate-700 mb-1">Телефон</label>
            <input id="phone" type="tel" inputMode="tel" placeholder="+380XXXXXXXXX" maxLength={13}
              autoComplete="tel" className={input}
              aria-invalid={!!errors.phone} aria-describedby={errors.phone ? 'phone-error' : undefined}
              value={phone} onChange={(e) => setPhone(e.target.value)} />
            {fieldError('phone')}
          </div>
          {error && <p role="alert" data-testid="form-error" className="text-red-600 text-sm">{error}</p>}
          {saved && <p role="status" className="text-green-700 text-sm">Зміни збережено</p>}
          <button type="submit" disabled={saving}
            className="bg-blue-700 hover:bg-blue-800 text-white font-bold px-5 py-2.5 rounded-xl disabled:opacity-60 transition-colors">
            {saving ? 'Зберігаємо...' : 'Зберегти'}
          </button>
        </form>
      </section>
    </div>
  );
}
