'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/lib/use-require-auth';
import { leadsApi } from '@/api/leads';
import { leadStatusLabel } from '@/lib/labels';
import type { Lead, PaginatedResponse } from '@/lib/types';
import Spinner from '@/components/ui/Spinner';

export default function MyLeadsPage() {
  const { user, loading } = useRequireAuth();
  const [data, setData] = useState<PaginatedResponse<Lead> | null>(null);
  const [fetching, setFetching] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!user) return;
    let alive = true;
    leadsApi.mine()
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setFailed(true); })
      .finally(() => { if (alive) setFetching(false); });
    return () => { alive = false; };
  }, [user]);

  if (loading || !user || fetching) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/me" className="text-blue-600 hover:underline text-sm">← Кабінет</Link>
        <h1 className="text-xl font-bold text-slate-900">Мої заявки</h1>
      </div>

      {failed ? (
        <p role="alert" className="text-red-600 bg-red-50 border border-red-200 rounded-xl p-4">
          Не вдалося завантажити заявки. Спробуйте оновити сторінку.
        </p>
      ) : !data || data.results.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-400 text-lg mb-4">Заявок ще немає</p>
          <Link href="/calculator" className="bg-blue-700 text-white px-6 py-2 rounded-xl font-semibold hover:bg-blue-800">
            Порахувати вартість
          </Link>
        </div>
      ) : (
        <ul className="space-y-4">
          {data.results.map((lead) => (
            <li key={lead.id} data-testid="lead-item" className="bg-white border border-slate-200 rounded-xl p-5">
              <div className="flex justify-between items-start gap-3">
                <div>
                  <p className="font-mono font-bold text-slate-900">{lead.public_id}</p>
                  <p className="text-xs text-slate-500">{new Date(lead.created_at).toLocaleString('uk-UA')}</p>
                  {lead.vehicle_label && <p className="text-sm text-slate-700 mt-1">{lead.vehicle_label}</p>}
                </div>
                <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded font-semibold">
                  {leadStatusLabel(lead.status, lead.status_display)}
                </span>
              </div>
              {(lead.total_usd || lead.total_uah) && (
                <p className="font-bold text-blue-800 mt-2">
                  {lead.total_usd ? `$${Number(lead.total_usd).toLocaleString('uk-UA')}` : ''}
                  {lead.total_usd && lead.total_uah ? ' / ' : ''}
                  {lead.total_uah ? `${Number(lead.total_uah).toLocaleString('uk-UA')} грн` : ''}
                </p>
              )}
              {lead.listing_id != null && (
                <Link href={`/listings/${lead.listing_id}`} className="text-sm text-blue-700 hover:underline mt-2 inline-block">
                  Переглянути лот →
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
