import { C2CGate, c2cMetadata } from '@/components/c2c/gates';

// Прапорець C2C приходить з API: рендер на кожен запит (інакше під час збірки запечеться «закрито»).
export const dynamic = 'force-dynamic';

export async function generateMetadata() {
  return c2cMetadata('posting');
}

export default async function Layout({ children }: { children: React.ReactNode }) {
  return <C2CGate level="posting">{children}</C2CGate>;
}
