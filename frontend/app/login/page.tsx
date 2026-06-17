'use client';
import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      await login(email, password);
      router.push('/me');
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10">
      <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900 mb-6">Вхід</h1>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">Email</label>
            <input type="email" required className="w-full border border-slate-300 rounded-lg px-3 py-2"
              value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">Пароль</label>
            <input type="password" required className="w-full border border-slate-300 rounded-lg px-3 py-2"
              value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button type="submit" disabled={loading}
            className="w-full bg-blue-700 hover:bg-blue-800 text-white font-bold py-2.5 rounded-xl disabled:opacity-60 transition-colors">
            {loading ? 'Вхід...' : 'Увійти'}
          </button>
        </form>
        <p className="mt-4 text-sm text-center text-slate-500">
          Немає акаунту? <Link href="/register" className="text-blue-600 hover:underline">Реєстрація</Link>
        </p>
      </div>
    </div>
  );
}
