'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import LocalListingForm from '@/components/local/LocalListingForm';

export default function NewLocalListingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.push('/login');
  }, [user, loading, router]);

  if (loading || !user) return null;

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Подати оголошення</h1>
      <p className="text-sm text-slate-500 mb-8">Розмістіть авто в Каталозі Україна — безкоштовно</p>
      <LocalListingForm />
    </div>
  );
}
