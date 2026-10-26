import type { Metadata } from 'next';
import { C2CGate } from '@/components/c2c/gates';

export const dynamic = 'force-dynamic';

// Приватні форми не індексуються незалежно від стану прапорців C2C.
export const metadata: Metadata = {
  title: 'Нове оголошення',
  robots: { index: false, follow: false },
};

export default async function Layout({ children }: { children: React.ReactNode }) {
  return <C2CGate level="posting" loginNext="/local/new">{children}</C2CGate>;
}
