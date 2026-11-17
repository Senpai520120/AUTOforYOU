'use client';
import { useRequireAuth } from '@/lib/use-require-auth';
import LoadingState from '@/components/ui/LoadingState';
import LocalListingForm from '@/components/local/LocalListingForm';

export default function NewLocalListingPage() {
  const { user, loading } = useRequireAuth();

  if (loading || !user) return <LoadingState />;

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Подати оголошення</h1>
      <p className="text-sm text-slate-500 mb-8">Розмістіть авто в Каталозі Україна — безкоштовно</p>
      <LocalListingForm />
    </div>
  );
}
