import { C2CGate, c2cMetadata } from '@/components/c2c/gates';

export const dynamic = 'force-dynamic';

export async function generateMetadata() {
  return c2cMetadata('posting');
}

export default async function Layout({ children }: { children: React.ReactNode }) {
  return <C2CGate level="posting" loginNext="/local/new">{children}</C2CGate>;
}
