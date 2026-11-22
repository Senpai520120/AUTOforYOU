import Link from 'next/link';

export default function AccessDenied() {
  return (
    <div className="max-w-md mx-auto text-center py-16">
      <h1 className="text-2xl font-bold text-foreground mb-3">Доступ обмежено</h1>
      <p className="text-muted-foreground mb-6">Ця сторінка доступна лише брокерам та адміністраторам.</p>
      <Link href="/me" className="text-link hover:underline">← Кабінет</Link>
    </div>
  );
}
