'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ApiError } from '@/api/client';
import { brokerLeadsApi } from '@/api/leads';
import { LEAD_STATUS_LABELS } from '@/lib/labels';
import { formatUsd } from '@/lib/format';
import type { BrokerLeadList as BrokerLeadListData, LeadStatus } from '@/lib/types';
import Spinner from '@/components/ui/Spinner';
import AccessDenied from './AccessDenied';
import LeadStatusBadge from './LeadStatusBadge';

const STATUSES = Object.keys(LEAD_STATUS_LABELS) as LeadStatus[];
const PAGE_SIZE = 20;
const fmt = (iso: string) => new Date(iso).toLocaleString('uk-UA');

export default function BrokerLeadList() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const status = sp.get('status') ?? '';
  const utmSource = sp.get('utm_source') ?? '';
  // Пошук (імʼя, телефон) — персональні дані: тримаємо лише в стані, не в URL сторінки.
  const mine = sp.get('assigned_to') === 'me';
  const page = Math.max(1, Number(sp.get('page') ?? '1') || 1);

  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [utmInput, setUtmInput] = useState(utmSource);
  const [data, setData] = useState<BrokerLeadListData | null>(null);
  const [fetching, setFetching] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [failed, setFailed] = useState(false);

  const setParams = (patch: Record<string, string>) => {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    if (!('page' in patch)) next.delete('page');
    const qs = next.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  };

  useEffect(() => {
    let alive = true;
    setFetching(true);
    setFailed(false);
    brokerLeadsApi.list({
      status, utm_source: utmSource, search, assigned_to: mine ? 'me' : '',
      page: page > 1 ? String(page) : '', page_size: String(PAGE_SIZE),
    })
      .then((d) => { if (alive) setData(d); })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 403) setForbidden(true);
        else setFailed(true);
      })
      .finally(() => { if (alive) setFetching(false); });
    return () => { alive = false; };
  }, [status, utmSource, search, mine, page]);

  if (forbidden) return <AccessDenied />;

  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Link href="/me" className="text-link hover:underline text-sm">← Кабінет</Link>
        <h1 className="text-xl font-bold text-foreground">Заявки</h1>
        {data && (
          <span data-testid="new-count" className="text-xs bg-warning/15 text-foreground px-2 py-1 rounded font-semibold">
            Нових: {data.new_count}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2 mb-4 min-w-0" role="group" aria-label="Фільтр за статусом">
        <button type="button" onClick={() => setParams({ status: '' })} aria-pressed={!status}
          className={`px-3 py-1 rounded-full text-sm border ${!status ? 'bg-primary text-primary-foreground border-primary' : 'bg-card text-foreground border-input'}`}>
          Усі
        </button>
        {STATUSES.map((s) => (
          <button key={s} type="button" onClick={() => setParams({ status: s })} aria-pressed={status === s}
            className={`px-3 py-1 rounded-full text-sm border ${status === s ? 'bg-primary text-primary-foreground border-primary' : 'bg-card text-foreground border-input'}`}>
            {LEAD_STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      <form className="flex flex-wrap items-end gap-3 mb-6 min-w-0"
        onSubmit={(e) => { e.preventDefault(); setSearch(searchInput.trim()); setParams({ utm_source: utmInput.trim() }); }}>
        <label className="text-sm text-foreground w-full min-w-0 sm:w-auto">
          <span className="block mb-1">Ім’я або телефон</span>
          <input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} maxLength={100}
            className="border border-input rounded-lg px-3 py-1.5 w-full min-w-0" />
        </label>
        <label className="text-sm text-foreground w-full min-w-0 sm:w-auto">
          <span className="block mb-1">Джерело (utm_source)</span>
          <input value={utmInput} onChange={(e) => setUtmInput(e.target.value)} maxLength={100}
            className="border border-input rounded-lg px-3 py-1.5 w-full min-w-0" />
        </label>
        <label className="text-sm text-foreground flex items-center gap-2 pb-2">
          <input type="checkbox" checked={mine} onChange={(e) => setParams({ assigned_to: e.target.checked ? 'me' : '' })} />
          Мої заявки
        </label>
        <button type="submit" className="bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-1.5 rounded-lg text-sm font-semibold">
          Знайти
        </button>
        <a href={brokerLeadsApi.exportUrl(status)}
          className="border border-link text-link hover:bg-link/10 px-4 py-1.5 rounded-lg text-sm font-semibold">
          Завантажити CSV
        </a>
      </form>

      {fetching ? (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      ) : failed ? (
        <p role="alert" className="text-destructive bg-destructive/10 border border-destructive/40 rounded-xl p-4">
          Не вдалося завантажити заявки. Спробуйте оновити сторінку.
        </p>
      ) : !data || data.results.length === 0 ? (
        <p className="text-center text-muted-foreground text-lg py-16">Заявок за цими умовами немає</p>
      ) : (
        <ul className="space-y-3">
          {data.results.map((lead) => (
            <li key={lead.id} data-testid="broker-lead-item">
              <Link href={`/broker/leads/${lead.id}`}
                className="block min-w-0 break-words bg-card border border-border rounded-xl p-4 hover:border-link/50 hover:shadow-sm">
                <div className="flex flex-wrap justify-between items-start gap-2">
                  <div className="min-w-0">
                    <p className="font-mono font-bold text-foreground">
                      {lead.public_id}
                      {lead.duplicate_of && (
                        <span data-testid="lead-duplicate-badge"
                          className="ml-2 align-middle rounded bg-warning/15 px-1.5 py-0.5 font-sans text-xs font-semibold text-foreground">
                          Повтор {lead.duplicate_of}
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">{fmt(lead.created_at)}</p>
                  </div>
                  <LeadStatusBadge status={lead.status} label={lead.status_display} />
                </div>
                <p className="mt-2 font-semibold text-foreground break-words">{lead.name}</p>
                <p className="text-sm text-foreground break-all">{lead.phone}</p>
                {lead.car && <p className="text-sm text-muted-foreground break-words">{lead.car}</p>}
                <dl className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <div><dt className="inline text-muted-foreground">Джерело: </dt><dd data-testid="lead-utm-source" className="inline break-all">{lead.utm_source || 'пряме'}</dd></div>
                  <div><dt className="inline text-muted-foreground">Перша реакція: </dt><dd className="inline">{lead.first_response_at ? fmt(lead.first_response_at) : 'ще немає'}</dd></div>
                  <div><dt className="inline text-muted-foreground">Відповідальний: </dt><dd className="inline break-all">{lead.assigned_to ? lead.assigned_to.name : '—'}</dd></div>
                  {(lead.total_usd_full ?? lead.total_usd) && <div><dt className="inline text-muted-foreground">Сума: </dt><dd className="inline break-all">{formatUsd((lead.total_usd_full ?? lead.total_usd) as string)} <span className="text-muted-foreground">з розмитненням, орієнтовно</span></dd></div>}
                </dl>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {data && pages > 1 && (
        <nav className="flex items-center justify-center gap-3 mt-6" aria-label="Сторінки">
          <button type="button" disabled={page <= 1} onClick={() => setParams({ page: String(page - 1) })}
            className="px-3 py-1 border border-input rounded-lg disabled:opacity-40">← Назад</button>
          <span className="text-sm text-muted-foreground">{page} / {pages}</span>
          <button type="button" disabled={page >= pages} onClick={() => setParams({ page: String(page + 1) })}
            className="px-3 py-1 border border-input rounded-lg disabled:opacity-40">Далі →</button>
        </nav>
      )}
    </div>
  );
}
