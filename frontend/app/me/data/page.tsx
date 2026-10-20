'use client';
import { useState } from 'react';
import Link from 'next/link';
import { ApiError } from '@/api/client';
import { meApi } from '@/api/me';
import { useRequireAuth } from '@/lib/use-require-auth';
import { formatDeletionDate, setFlash } from '@/lib/deletion';

export default function MyDataPage() {
  const { user, loading, refreshUser } = useRequireAuth();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const [password, setPassword] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [cancelError, setCancelError] = useState('');

  if (loading || !user) return null;

  const download = async () => {
    setExporting(true); setExportError('');
    try {
      await meApi.exportData();
    } catch (err) {
      setExportError(err instanceof ApiError && err.status === 429
        ? 'Вивантаження доступне кілька разів на добу. Спробуйте пізніше.'
        : 'Не вдалося завантажити дані. Спробуйте пізніше.');
    } finally {
      setExporting(false);
    }
  };

  const remove = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || !confirmed) return;
    setDeleting(true); setDeleteError('');
    try {
      const { deletion_scheduled_for } = await meApi.deleteAccount(password);
      setFlash(
        `Видалення акаунта заплановано на ${formatDeletionDate(deletion_scheduled_for)}. `
        + 'До цієї дати можна увійти й скасувати видалення.',
      );
      // Сервер уже відкликав сесії й видалив cookie: повне перезавантаження очищає дані вкладки.
      window.location.assign('/');
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        const pwd = (err.data as { password?: unknown } | null)?.password;
        setDeleteError(Array.isArray(pwd) ? String(pwd[0]) : (err.message || 'Не вдалося видалити акаунт.'));
      } else if (err instanceof ApiError && err.status === 429) {
        setDeleteError('Забагато спроб. Спробуйте пізніше.');
      } else {
        setDeleteError('Не вдалося видалити акаунт. Спробуйте пізніше.');
      }
      setDeleting(false);
    }
  };

  const cancel = async () => {
    setCancelError('');
    try {
      await meApi.cancelDeletion();
      await refreshUser();
    } catch {
      setCancelError('Не вдалося скасувати видалення. Спробуйте ще раз.');
    }
  };

  const scheduled = user.deletion_scheduled_for;
  return (
    <div className="max-w-2xl mx-auto">
      <Link href="/me" className="text-sm text-blue-600 hover:underline">← До кабінету</Link>
      <h1 className="text-2xl font-bold text-slate-900 mt-2 mb-6">Мої дані</h1>

      <section className="bg-white border border-slate-200 rounded-2xl p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-2">Копія моїх даних</h2>
        <p className="text-sm text-slate-500 mb-4">
          Файл JSON з профілем, оголошеннями, заявками, розрахунками, перепискою, угодами, платежами
          та журналом ваших згод. Інших користувачів у файлі видно лише за відображуваним ім&apos;ям.
        </p>
        {exportError && <p role="alert" className="text-red-600 text-sm mb-2">{exportError}</p>}
        <button type="button" onClick={download} disabled={exporting}
          className="bg-blue-700 hover:bg-blue-800 text-white font-bold px-5 py-2.5 rounded-xl disabled:opacity-60 transition-colors">
          {exporting ? 'Готуємо файл...' : 'Завантажити мої дані'}
        </button>
      </section>

      <section className="bg-white border border-red-200 rounded-2xl p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-2">Видалити акаунт</h2>
        {scheduled ? (
          <div data-testid="deletion-scheduled">
            <p className="text-sm text-slate-700 mb-4">
              Акаунт буде видалено {formatDeletionDate(scheduled)}. Зняті оголошення лишаються знятими —
              після скасування опублікуйте їх знову.
            </p>
            {cancelError && <p role="alert" className="text-red-600 text-sm mb-2">{cancelError}</p>}
            <button type="button" onClick={cancel}
              className="bg-blue-700 hover:bg-blue-800 text-white font-bold px-5 py-2.5 rounded-xl transition-colors">
              Скасувати видалення
            </button>
          </div>
        ) : (
          <form onSubmit={remove} className="space-y-4">
            <p className="text-sm text-slate-500">
              Оголошення одразу знімаються з публікації, усі пристрої виходять з акаунта. Протягом
              періоду скасування видалення можна скасувати. Після нього ім&apos;я, телефон і email
              стираються, угоди й платежі зберігаються у знеособленому вигляді.
            </p>
            <div>
              <label htmlFor="delete-password" className="block text-sm font-semibold text-slate-700 mb-1">Пароль</label>
              <input id="delete-password" type="password" autoComplete="current-password"
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
                value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input type="checkbox" className="mt-1" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
              <span>Я розумію, що це незворотно</span>
            </label>
            {deleteError && <p role="alert" data-testid="delete-error" className="text-red-600 text-sm">{deleteError}</p>}
            <button type="submit" disabled={!password || !confirmed || deleting}
              className="bg-red-600 hover:bg-red-700 text-white font-bold px-5 py-2.5 rounded-xl disabled:opacity-50 transition-colors">
              {deleting ? 'Видаляємо...' : 'Видалити акаунт'}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
