import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Реєстрація',
  robots: { index: false },
};

export default function RegisterLayout({ children }: { children: React.ReactNode }) {
  return children;
}
