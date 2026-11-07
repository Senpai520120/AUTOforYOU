'use client';
/**
 * Форма заявки брокеру (задача 2.3). Одна форма для калькулятора, лота і (далі) лендінгів.
 * Гість не втрачає введене: 401 тут не веде на /login (api/client не редиректить).
 */
import { trackEvent } from '@/lib/analytics';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { apiGet, ApiError } from '@/api/client';
import { leadsApi } from '@/api/leads';
import { useAuth } from '@/lib/auth-context';
import { getAttribution } from '@/lib/attribution';
import { isCaptchaFailed, useAuthConfig, useCaptchaState } from '@/lib/captcha';
import type { LeadContactMethod, LeadCreate, LeadNeededWhen, LeadSource, SiteSettings } from '@/lib/types';
import Captcha from '@/components/ui/Captcha';
import LeadSuccess from './LeadSuccess';

interface Props {
  source: LeadSource;
  calculationId?: number;
  listingId?: number;
  landingSlug?: string;
  vehicleLabel?: string;
  /** Бюджет, що підставляється у поле (лендінг моделі); клієнт може змінити. */
  defaultBudgetUsd?: string;
  /** Кнопка на екрані успіху (напр. «Новий розрахунок»); без неї кнопки немає. */
  onNew?: () => void;
  newLabel?: string;
}

type Errors = Record<string, string>;

const METHODS: { value: LeadContactMethod; label: string }[] = [
  { value: 'phone', label: 'Дзвінок' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'viber', label: 'Viber' },
];
const NEEDED: { value: LeadNeededWhen; label: string }[] = [
  { value: 'asap', label: 'Якнайшвидше' },
  { value: 'month', label: 'Протягом місяця' },
  { value: 'three_months', label: 'Протягом 3 місяців' },
  { value: 'later', label: 'Пізніше / поки придивляюсь' },
];
const FIELDS = [
  'name', 'phone', 'email', 'contact_method', 'contact_handle', 'comment',
  'budget_usd', 'needed_when', 'city', 'consent', 'partner_consent',
];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const INPUT = 'w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500';
const GENERAL_ERROR = 'Не вдалося надіслати заявку. Спробуйте ще раз пізніше.';

function FieldError({ id, text }: { id: string; text?: string }) {
  if (!text) return null;
  return <p id={id} role="alert" className="text-red-600 text-xs mt-1">{text}</p>;
}

/** Помилки 400 за полями; решта ключів (calculation_id, source…) — у загальні. */
function parseFieldErrors(data: unknown): { fields: Errors; general: string[] } {
  const fields: Errors = {};
  const general: string[] = [];
  if (!data || typeof data !== 'object') return { fields, general };
  for (const [key, raw] of Object.entries(data as Record<string, unknown>)) {
    if (key === 'code') continue;
    const first = Array.isArray(raw) ? raw[0] : raw;
    if (typeof first !== 'string') continue;
    if (FIELDS.includes(key)) fields[key] = first;
    else general.push(first);
  }
  return { fields, general };
}

export default function LeadForm({
  source, calculationId, listingId, landingSlug, vehicleLabel, defaultBudgetUsd, onNew, newLabel,
}: Props) {
  const { user } = useAuth();
  const { config } = useAuthConfig();
  const captcha = useCaptchaState();
  const touched = useRef({ name: false, phone: false });

  const [consentText, setConsentText] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [method, setMethod] = useState<LeadContactMethod>('phone');
  const [handle, setHandle] = useState('');
  const [comment, setComment] = useState('');
  const [more, setMore] = useState(!!defaultBudgetUsd);
  const [budget, setBudget] = useState(defaultBudgetUsd ?? '');
  const [needed, setNeeded] = useState<LeadNeededWhen | ''>('');
  const [city, setCity] = useState('');
  const [consent, setConsent] = useState(false);
  const [partnerConsent, setPartnerConsent] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [general, setGeneral] = useState('');
  const [publicId, setPublicId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    apiGet<SiteSettings>('/api/v1/site-settings/')
      .then((s) => { if (alive) setConsentText(s.partner_consent_text?.trim() ?? ''); })
      .catch(() => { if (alive) setConsentText(''); });
    return () => { alive = false; };
  }, []);

  // Передзаповнення з профілю: лише поки користувач сам не чіпав поле.
  useEffect(() => {
    if (!user) return;
    if (!touched.current.name) setName([user.first_name, user.last_name].filter(Boolean).join(' '));
    if (!touched.current.phone) setPhone(user.phone ?? '');
  }, [user]);

  if (publicId) return <LeadSuccess publicId={publicId} onNew={onNew} newLabel={newLabel} />;

  const partnerReady = !!consentText;
  const canSubmit = captcha.ready && partnerReady && partnerConsent && !submitting;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    const local: Errors = {};
    if (!name.trim()) local.name = "Вкажіть ім'я.";
    if (!phone.trim()) local.phone = 'Вкажіть телефон.';
    if (email.trim() && !EMAIL_RE.test(email.trim())) local.email = 'Вкажіть коректний email.';
    if (!consent) local.consent = 'Потрібна згода на обробку персональних даних.';
    setGeneral('');
    setErrors(local);
    if (Object.keys(local).length) return;

    const attribution = getAttribution();
    const payload: LeadCreate = {
      name: name.trim(),
      phone: phone.trim(),
      contact_method: method,
      source,
      consent,
      partner_consent: partnerConsent,
      page_url: window.location.pathname,
      ...(email.trim() ? { email: email.trim() } : {}),
      ...(handle.trim() ? { contact_handle: handle.trim() } : {}),
      ...(comment.trim() ? { comment: comment.trim() } : {}),
      ...(budget.trim() ? { budget_usd: budget.trim() } : {}),
      ...(needed ? { needed_when: needed } : {}),
      ...(city.trim() ? { city: city.trim() } : {}),
      ...(calculationId != null ? { calculation_id: calculationId } : {}),
      ...(listingId != null ? { listing_id: listingId } : {}),
      ...(landingSlug ? { landing_slug: landingSlug } : {}),
      ...(vehicleLabel ? { vehicle_label: vehicleLabel } : {}),
      ...attribution,
      ...captcha.payload(),
    };

    setSubmitting(true);
    try {
      const created = await leadsApi.create(payload);
      setPublicId(created.public_id);
      trackEvent('lead_submit', { source }); // лише категорія джерела, без ПДн
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        if (isCaptchaFailed(err)) {
          setGeneral('Не вдалося пройти перевірку. Спробуйте ще раз.');
        } else {
          const parsed = parseFieldErrors(err.data);
          setErrors(parsed.fields);
          setGeneral(parsed.general.join(' ') || (Object.keys(parsed.fields).length ? '' : GENERAL_ERROR));
        }
      } else if (err instanceof ApiError && err.status === 429) {
        setGeneral('Забагато заявок, спробуйте пізніше.');
      } else if (err instanceof ApiError && err.status === 503) {
        setGeneral('Прийом заявок тимчасово недоступний. Спробуйте пізніше.');
      } else {
        setGeneral(GENERAL_ERROR);
      }
    } finally {
      setSubmitting(false);
      captcha.bump(); // токен одноразовий: новий після кожної відповіді сервера
    }
  };

  return (
    <form onSubmit={submit} noValidate data-testid="lead-form"
      className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
      <h3 className="font-bold text-slate-900 text-lg">Залишити заявку брокеру</h3>
      {vehicleLabel && landingSlug && (
        <p data-testid="lead-vehicle" className="text-sm text-slate-700">
          Авто: <span className="font-semibold">{vehicleLabel}</span>
        </p>
      )}

      <div>
        <label htmlFor="lead-name" className="block text-xs font-semibold text-slate-600 mb-1">Ім&apos;я *</label>
        <input id="lead-name" name="name" required maxLength={100} autoComplete="name" className={INPUT}
          value={name} aria-invalid={!!errors.name} aria-describedby={errors.name ? 'lead-name-err' : undefined}
          onChange={(e) => { touched.current.name = true; setName(e.target.value); }} />
        <FieldError id="lead-name-err" text={errors.name} />
      </div>

      <div>
        <label htmlFor="lead-phone" className="block text-xs font-semibold text-slate-600 mb-1">Телефон *</label>
        <input id="lead-phone" name="phone" type="tel" inputMode="tel" required maxLength={32}
          autoComplete="tel" placeholder="+380…" className={INPUT}
          value={phone} aria-invalid={!!errors.phone} aria-describedby={errors.phone ? 'lead-phone-err' : undefined}
          onChange={(e) => { touched.current.phone = true; setPhone(e.target.value); }} />
        <FieldError id="lead-phone-err" text={errors.phone} />
      </div>

      <div>
        <label htmlFor="lead-email" className="block text-xs font-semibold text-slate-600 mb-1">Email (необов&apos;язково)</label>
        <input id="lead-email" name="email" type="email" maxLength={254} autoComplete="email" className={INPUT}
          value={email} aria-invalid={!!errors.email} aria-describedby="lead-email-hint"
          onChange={(e) => setEmail(e.target.value)} />
        <p id="lead-email-hint" className="text-xs text-slate-500 mt-1">
          На нього надійде копія розрахунку та статуси заявки.
        </p>
        <FieldError id="lead-email-err" text={errors.email} />
      </div>

      <fieldset>
        <legend className="block text-xs font-semibold text-slate-600 mb-1">Зручний спосіб зв&apos;язку</legend>
        <div className="flex gap-4 flex-wrap">
          {METHODS.map((m) => (
            <label key={m.value} htmlFor={`lead-method-${m.value}`} className="flex items-center gap-2 text-sm text-slate-700">
              <input id={`lead-method-${m.value}`} type="radio" name="contact_method" value={m.value}
                checked={method === m.value} onChange={() => setMethod(m.value)} />
              {m.label}
            </label>
          ))}
        </div>
        <FieldError id="lead-method-err" text={errors.contact_method} />
      </fieldset>

      {method !== 'phone' && (
        <div>
          <label htmlFor="lead-handle" className="block text-xs font-semibold text-slate-600 mb-1">
            Нік або контакт у {method === 'telegram' ? 'Telegram' : 'Viber'} (необов&apos;язково)
          </label>
          <input id="lead-handle" name="contact_handle" maxLength={64} className={INPUT}
            value={handle} onChange={(e) => setHandle(e.target.value)} />
          <FieldError id="lead-handle-err" text={errors.contact_handle} />
        </div>
      )}

      <div>
        <label htmlFor="lead-comment" className="block text-xs font-semibold text-slate-600 mb-1">Коментар</label>
        <textarea id="lead-comment" name="comment" rows={3} maxLength={1000} className={INPUT}
          value={comment} onChange={(e) => setComment(e.target.value)} />
        <FieldError id="lead-comment-err" text={errors.comment} />
      </div>

      <div>
        <button type="button" aria-expanded={more} onClick={() => setMore((v) => !v)}
          className="text-sm text-blue-700 hover:underline">
          {more ? 'Менше' : 'Ще'}
        </button>
        {more && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label htmlFor="lead-budget" className="block text-xs font-semibold text-slate-600 mb-1">Бюджет під ключ ($)</label>
              <input id="lead-budget" name="budget_usd" inputMode="decimal" className={INPUT}
                value={budget} onChange={(e) => setBudget(e.target.value)} />
              <FieldError id="lead-budget-err" text={errors.budget_usd} />
            </div>
            <div>
              <label htmlFor="lead-needed" className="block text-xs font-semibold text-slate-600 mb-1">Коли потрібне авто</label>
              <select id="lead-needed" name="needed_when" className={INPUT} value={needed}
                onChange={(e) => setNeeded(e.target.value as LeadNeededWhen | '')}>
                <option value="">Не вказано</option>
                {NEEDED.map((n) => <option key={n.value} value={n.value}>{n.label}</option>)}
              </select>
              <FieldError id="lead-needed-err" text={errors.needed_when} />
            </div>
            <div>
              <label htmlFor="lead-city" className="block text-xs font-semibold text-slate-600 mb-1">Місто</label>
              <input id="lead-city" name="city" maxLength={100} className={INPUT}
                value={city} onChange={(e) => setCity(e.target.value)} />
              <FieldError id="lead-city-err" text={errors.city} />
            </div>
          </div>
        )}
      </div>

      <div>
        <label htmlFor="lead-consent" className="flex items-start gap-2 text-sm text-slate-700">
          <input id="lead-consent" name="consent" type="checkbox" className="mt-1" checked={consent}
            aria-invalid={!!errors.consent} aria-describedby={errors.consent ? 'lead-consent-err' : undefined}
            onChange={(e) => setConsent(e.target.checked)} />
          <span>
            Погоджуюсь на обробку персональних даних відповідно до{' '}
            <Link href="/privacy" target="_blank" className="text-blue-700 underline">політики конфіденційності</Link>
          </span>
        </label>
        <FieldError id="lead-consent-err" text={errors.consent} />
      </div>

      <div>
        <label htmlFor="lead-partner-consent" className="flex items-start gap-2 text-sm text-slate-700">
          <input id="lead-partner-consent" name="partner_consent" type="checkbox" className="mt-1"
            checked={partnerConsent} disabled={!partnerReady}
            aria-invalid={!!errors.partner_consent}
            onChange={(e) => setPartnerConsent(e.target.checked)} />
          <span data-testid="partner-consent-text">{consentText || 'Згода на передачу контактів партнеру'}</span>
        </label>
        {consentText === '' && (
          <p role="status" className="text-amber-700 text-xs mt-1">
            Прийом заявок тимчасово недоступний: партнера ще не налаштовано.
          </p>
        )}
        <FieldError id="lead-partner-err" text={errors.partner_consent} />
      </div>

      {/* Honeypot: у режимі honeypot поле малює Captcha, в інших — тут. */}
      {config?.captcha.provider !== 'honeypot' && (
        <div aria-hidden="true" style={{ position: 'absolute', left: '-10000px', width: 1, height: 1, overflow: 'hidden' }}>
          <input type="text" name="website" tabIndex={-1} autoComplete="off" defaultValue=""
            onChange={(e) => captcha.setWebsite(e.target.value)} />
        </div>
      )}
      <Captcha config={config?.captcha ?? null} onToken={captcha.setToken}
        resetKey={captcha.resetKey} onHoneypot={captcha.setWebsite} />

      {general && (
        <p role="alert" className="text-red-600 text-sm bg-red-50 border border-red-200 rounded p-3">{general}</p>
      )}

      <button type="submit" disabled={!canSubmit}
        className="w-full bg-blue-700 hover:bg-blue-800 disabled:opacity-60 text-white font-bold py-3 rounded-xl transition-colors">
        {submitting ? 'Надсилаю…' : 'Надіслати'}
      </button>
    </form>
  );
}
