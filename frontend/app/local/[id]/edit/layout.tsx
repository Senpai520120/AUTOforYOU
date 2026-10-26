import type { Metadata } from 'next';
import { C2CGate } from '@/components/c2c/gates';

export const dynamic = 'force-dynamic';

// Приватні форми не індексуються незалежно від стану прапорців C2C.
export const metadata: Metadata = {
  title: 'Редагування оголошення',
  robots: { index: false, follow: false },
};

export default async function Layout({
  children, params,
}: { children: React.ReactNode; params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <C2CGate level="posting" loginNext={`/local/${encodeURIComponent(id)}/edit`}>{children}</C2CGate>
  );
}
