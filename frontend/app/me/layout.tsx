import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Особистий кабінет',
  robots: { index: false },
};

export default function MeLayout({ children }: { children: React.ReactNode }) {
  return children;
}
