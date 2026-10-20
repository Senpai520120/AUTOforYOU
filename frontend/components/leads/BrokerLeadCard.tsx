'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ApiError } from '@/api/client';
import { brokerLeadsApi } from '@/api/leads';
import { leadStatusLabel } from '@/lib/labels';
import type { BrokerLeadDetail, LeadPartnerStatus, LeadStatus } from '@/lib/types';
import Spinner from '@/components/ui/Spinner';
import AccessDenied from './AccessDenied';
import LeadStatusBadge from './LeadStatusBadge';

const fmt = (iso: string) => new Date(iso).toLocaleString('uk-UA');
const TG_HANDLE = /^@?[A-Za-z0-9_]{3,32}$/;

const PARTNER_STATUSES: { value: LeadPartnerStatus; label: string }[] = [
  { value: '', label: '—' },
  { value: 'no_answer', label: 'Не додзвонились' },
  { value: 'thinking', label: 'Думає' },
  { value: 'deposit', label: 'Депозит' },
  { value: 'bought', label: 'Куплено' },
  { value: 'rejected', label: 'Відмова' },
];

function interval(fromIso: string, toIso: string): string {
  const mins = Math.max(0, Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60000));
  if (mins < 60) return `${mins} хв`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours} год ${mins % 60} хв`;
  return `${Math.floor(hours / 24)} дн`;
}

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = (e.data as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string' && detail) return detail;
  }
  return 'Не вдалося виконати дію. Спробуйте ще раз.';
}

function ContactLinks({ lead }: { lead: BrokerLeadDetail }) {
  const digits = lead.phone.replace(/\D/g, '');
  return (
    <div className="space-y-1 text-sm">
      <p>
        Телефон: <a href={`tel:${lead.phone}`} className="text-blue-700 hover:underline font-semibold">{lead.phone}</a>
      </p>
      {lead.email && <p>Email: <span className="break-all">{lead.email}</span></p>}
      <p>Спосіб звʼязку: <strong>{lead.contact_method_display || '—'}</strong></p>
      {lead.contact_method === 'telegram' && lead.contact_handle && (
        TG_HANDLE.test(lead.contact_handle)
          ? <p>Telegram: <a href={`https://t.me/${lead.contact_handle.replace(/^@/, '')}`} target="_blank" rel="noopener noreferrer"
              className="text-blue-700 hover:underline">{lead.contact_handle}</a></p>
          : <p>Telegram: <span className="break-all">{lead.contact_handle}</span></p>
      )}
      {lead.contact_method === 'viber' && (
        <p>Viber: <a href={`viber://chat?number=%2B${digits}`} className="text-blue-700 hover:underline">{lead.phone}</a></p>
      )}
      {lead.contact_method !== 'telegram' && lead.contact_handle && (
        <p>Контакт: <span className="break-all">{lead.contact_handle}</span></p>
      )}
    </div>
  );
}

function FirstResponse({ lead }: { lead: BrokerLeadDetail }) {
  if (lead.first_response_at) {
    return <>{fmt(lead.first_response_at)} (через {interval(lead.created_at, lead.first_response_at)})</>;
  }
  return <>{lead.status === 'spam' ? 'не враховується' : 'ще немає'}</>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <h2 className="font-bold text-slate-900 mb-3">{title}</h2>
      {children}
    </section>
  );
}

function Snapshot({ lead }: { lead: BrokerLeadDetail }) {
  const snap = lead.calculation_snapshot ?? {};
  const breakdown = Object.entries(snap.breakdown ?? {});
  if (!snap.total_usd && breakdown.length === 0) return <p className="text-sm text-slate-500">Розрахунку немає</p>;
  return (
    <div className="text-sm">
      {snap.created_at && <p className="text-slate-500 mb-2">Курси на {fmt(snap.created_at)}</p>}
      {breakdown.length > 0 && (
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
          {breakdown.map(([k, v]) => (
            <div key={k} className="contents"><dt className="text-slate-600 break-words">{k}</dt><dd className="text-right">{String(v)}</dd></div>
          ))}
        </dl>
      )}
      {snap.total_usd && (
        <p className="mt-2 font-bold">Разом: ${Number(snap.total_usd).toLocaleString('uk-UA')}
          {snap.total_uah ? ` (≈ ${Number(snap.total_uah).toLocaleString('uk-UA')} грн)` : ''}
          {snap.is_estimate ? ' — орієнтовно' : ''}</p>
      )}
    </div>
  );
}

export default function BrokerLeadCard({ id }: { id: number }) {
  const [lead, setLead] = useState<BrokerLeadDetail | null>(null);
  const [fetching, setFetching] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const load = useCallback(() => {
    setFetching(true);
    brokerLeadsApi.detail(id)
      .then((d) => { setLead(d); setLoadError(''); })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setForbidden(true);
        else if (e instanceof ApiError && e.status === 404) setLoadError('Заявку не знайдено.');
        else setLoadError('Не вдалося завантажити заявку. Спробуйте оновити сторінку.');
      })
      .finally(() => setFetching(false));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Без оптимістичного оновлення: екран змінюється лише з відповіді сервера.
  const act = async (fn: () => Promise<BrokerLeadDetail>, clearNote = false) => {
    setBusy(true);
    setActionError('');
    try {
      setLead(await fn());
      if (clearNote) setNote('');
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  if (forbidden) return <AccessDenied />;
  if (fetching && !lead) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>;
  if (!lead) {
    return (
      <div>
        <Link href="/broker/leads" className="text-blue-600 hover:underline text-sm">← Заявки</Link>
        <p role="alert" className="mt-4 text-red-600 bg-red-50 border border-red-200 rounded-xl p-4">{loadError}</p>
      </div>
    );
  }

  const canTake = !lead.assigned_to && ['new', 'in_progress'].includes(lead.status);
  const transitions = lead.allowed_transitions.filter((s) => !(canTake && lead.status === 'new' && s === 'in_progress'));
  const utmEntries = Object.entries(lead.utm ?? {});

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/broker/leads" className="text-blue-600 hover:underline text-sm">← Заявки</Link>
        <h1 className="text-xl font-bold text-slate-900 font-mono">{lead.public_id}</h1>
        <LeadStatusBadge status={lead.status} label={lead.status_display} />
      </div>

      <Section title="Клієнт">
        <p className="font-semibold text-slate-900 mb-2 break-words">{lead.name}</p>
        <ContactLinks lead={lead} />
        {lead.comment && <p className="mt-3 text-sm text-slate-700 whitespace-pre-wrap break-words">Коментар: {lead.comment}</p>}
        <dl className="mt-3 text-sm text-slate-600 space-y-1">
          {lead.city && <div>Місто: {lead.city}</div>}
          {lead.budget_usd && <div>Бюджет: ${Number(lead.budget_usd).toLocaleString('uk-UA')}</div>}
          {lead.needed_when_display && <div>Коли потрібне авто: {lead.needed_when_display}</div>}
          <div>Партнер: {lead.partner_name}</div>
        </dl>
      </Section>

      <Section title="Авто та розрахунок">
        {lead.car && <p className="text-sm font-semibold mb-2 break-words">{lead.car}</p>}
        {lead.listing && <p className="text-sm mb-2"><Link href={lead.listing.url} className="text-blue-700 hover:underline">Відкрити лот #{lead.listing.id}</Link></p>}
        <Snapshot lead={lead} />
      </Section>

      <Section title="Джерело заявки">
        <dl data-testid="lead-source-block" className="text-sm space-y-1">
          <div>Точка входу: {lead.source_display}</div>
          {utmEntries.length === 0 ? <div>UTM: пряме</div> : utmEntries.map(([k, v]) => (
            <div key={k}>UTM {k}: <span data-testid={`utm-${k}`} className="break-all">{v}</span></div>
          ))}
          <div>Реферер: <span className="break-all">{lead.referrer || '—'}</span></div>
          <div>Сторінка входу: <span className="break-all">{lead.entry_page_url || '—'}</span></div>
          <div>Сторінка заявки: <span className="break-all">{lead.page_url || '—'}</span></div>
          <div data-testid="first-response">Перша реакція: <FirstResponse lead={lead} /></div>
        </dl>
      </Section>

      <Section title="Робота із заявкою">
        <p className="text-sm text-slate-600 mb-3">
          Відповідальний: {lead.assigned_to ? lead.assigned_to.name : 'не призначено'}
        </p>
        {actionError && <p role="alert" className="mb-3 text-red-700 bg-red-50 border border-red-200 rounded-lg p-3 text-sm">{actionError}</p>}
        {canTake && (
          <button type="button" disabled={busy} onClick={() => act(() => brokerLeadsApi.take(lead.id))}
            className="mb-3 bg-blue-700 hover:bg-blue-800 disabled:opacity-60 text-white px-4 py-2 rounded-lg font-semibold">
            Взяти в роботу
          </button>
        )}
        {transitions.length > 0 ? (
          <>
            <label className="block text-sm text-slate-700 mb-3">
              <span className="block mb-1">Нотатка до зміни статусу</span>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2}
                className="border border-slate-300 rounded-lg px-3 py-2 w-full" />
            </label>
            <div className="flex flex-wrap gap-2">
              {transitions.map((s: LeadStatus) => (
                <button key={s} type="button" disabled={busy} onClick={() => act(() => brokerLeadsApi.setStatus(lead.id, s, note), true)}
                  className="border border-blue-700 text-blue-800 hover:bg-blue-50 disabled:opacity-60 px-3 py-1.5 rounded-lg text-sm font-semibold">
                  {leadStatusLabel(s)}
                </button>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-500">Заявку закрито, переходів немає.</p>
        )}
        <label className="block text-sm text-slate-700 mt-4">
          <span className="block mb-1">Статус за словами партнера</span>
          <select value={lead.partner_status} disabled={busy}
            onChange={(e) => act(() => brokerLeadsApi.setPartnerStatus(lead.id, e.target.value as LeadPartnerStatus))}
            className="border border-slate-300 rounded-lg px-3 py-1.5">
            {PARTNER_STATUSES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </label>
      </Section>

      <Section title="Журнал статусів">
        <ol data-testid="lead-history" className="space-y-2 text-sm">
          {lead.history.map((h) => (
            <li key={h.id} data-testid="history-item" className="border-l-2 border-blue-200 pl-3">
              <p className="text-slate-900">
                {h.from_status_display ? `${h.from_status_display} → ` : ''}<strong>{h.to_status_display}</strong>
              </p>
              <p className="text-xs text-slate-500">{fmt(h.created_at)} · {h.changed_by ? h.changed_by.name : 'клієнт / система'}</p>
              {h.note && <p className="text-slate-700 break-words">{h.note}</p>}
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}
