import Link from 'next/link';
import type { Crumb } from '@/lib/jsonld';

/**
 * Видимі хлібні крихти (задача 10.9). Приймає той самий масив {name, path}, що й breadcrumbLd,
 * тож HTML і JSON-LD не розходяться. Остання крихта — поточна сторінка: без посилання, aria-current.
 * Роздільник декоративний (aria-hidden).
 */
export default function Breadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  const items = crumbs.filter((c) => c.name);
  if (items.length === 0) return null;
  return (
    <nav aria-label="Хлібні крихти" data-testid="breadcrumbs" className="text-sm text-muted-foreground">
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <li key={c.path} className="flex items-center gap-2" data-testid="breadcrumb">
              {i > 0 && <span aria-hidden="true" className="text-muted-foreground">›</span>}
              {last ? (
                <span aria-current="page" className="font-semibold text-foreground">{c.name}</span>
              ) : (
                <Link href={c.path} className="text-primary underline underline-offset-2 hover:text-primary/80">
                  {c.name}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
