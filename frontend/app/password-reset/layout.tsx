import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Скидання пароля',
  robots: { index: false },
};

export default function PasswordResetLayout({ children }: { children: React.ReactNode }) {
  return children;
}
