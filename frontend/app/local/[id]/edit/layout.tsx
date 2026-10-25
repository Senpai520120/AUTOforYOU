import { C2CGate, c2cMetadata } from '@/components/c2c/gates';

export const dynamic = 'force-dynamic';

export async function generateMetadata() {
  return c2cMetadata('posting');
}

export default async function Layout({
  children, params,
}: { children: React.ReactNode; params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <C2CGate level="posting" loginNext={`/local/${encodeURIComponent(id)}/edit`}>{children}</C2CGate>
  );
}
