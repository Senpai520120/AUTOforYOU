'use client';
/**
 * Форма заявки брокеру (задача 2.3). Одна форма для калькулятора, лота і (далі) лендінгів.
 * Гість не втрачає введене: 401 тут не веде на /login (api/client не редиректить).
 */
import { trackEvent } from '@/lib/analytics';
import { sendMetric } from '@/lib/metrics';
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ApiError } from '@/api/client';
import { fetchSiteSettings } from '@/lib/site-settings-client';
import { leadsApi } from '@/api/leads';
import { useAuth } from '@/lib/auth-context';
import { getAttribution } from '@/lib/attribution';
import { isCaptchaFailed, useAuthConfig, useCaptchaState } from '@/lib/captcha';
import type { LeadContactMethod, LeadCreate, LeadNeededWhen, LeadSource, SiteSettings } from '@/lib/types';
import Captcha from '@/components/ui/Captcha';
import FallbackContact, { ContactList } from '@/components/ui/FallbackContact';
import LeadSuccess from './LeadSuccess';
import { CircleAlert, ChevronDown, Send, TriangleAlert } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Textarea } from '@/components/shadcn/textarea';
import { FIELD_CLASS } from '@/components/local/field-classes';
import { ICON_STROKE } from '@/lib/utils';

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
/** Поля другого (необов'язкового) кроку: помилка в них розкриває блок. */
const DETAIL_FIELDS = ['email', 'comment', 'budget_usd', 'needed_when', 'city'];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const GENERAL_ERROR = 'Не вдалося надіслати заявку. Спробуйте ще раз пізніше.';

/** UUID v4; crypto.randomUUID недоступний у незахищеному контексті (http), тоді - getRandomValues. */
function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

function FieldError({ id, text }: { id: string; text?: string }) {
  if (!text) return null;
  return (
    <p id={id} role="alert" className="mt-1.5 flex items-start gap-1.5 text-sm text-destructive">
      <CircleAlert className="mt-0.5 size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
      <span>{text}</span>
    </p>
  );
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
  const [siteSettings, setSiteSettings] = useState<SiteSettings | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [serverDown, setServerDown] = useState(false);
  const loadingRef = useRef(false);
  // Ключ ідемпотентності однієї відправки (10.13): не змінюється при помилках, змінюється після успіху.
  const keyRef = useRef<string | null>(null);
  const inFlightRef = useRef(false);
  // Старт форми рахуємо один раз на ключ відправки (лічильник без ПДн, 10.15).
  const startedRef = useRef(false);
  const aliveRef = useRef(true);
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
  const formRef = useRef<HTMLFormElement>(null);
  // Лічильник «показати першу помилку»: змінюється при кожній невдалій відправці (клієнтській чи серверній).
  const [focusTick, setFocusTick] = useState(0);

  // Завантаження налаштувань сайту; повтор не створює паралельних запитів.
  const loadSettings = useCallback(async (force = false) => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setRetrying(true);
    try {
      const st = await fetchSiteSettings(force);
      if (!aliveRef.current) return;
      setSiteSettings(st);
      setConsentText(st.partner_consent_text?.trim() ?? '');
    } catch {
      if (!aliveRef.current) return;
      setSiteSettings(null);
      setConsentText('');
    } finally {
      loadingRef.current = false;
      if (aliveRef.current) setRetrying(false);
    }
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSettings();
    return () => { aliveRef.current = false; };
  }, [loadSettings]);

  const retry = async () => {
    setServerDown(false);
    setGeneral('');
    await loadSettings(true);
  };

  // Передзаповнення з профілю: лише поки користувач сам не чіпав поле.
  useEffect(() => {
    if (!user) return;
    if (!touched.current.name) setName([user.first_name, user.last_name].filter(Boolean).join(' '));
    if (!touched.current.phone) setPhone(user.phone ?? '');
  }, [user]);

  // Фокус і прокрутка до першого поля з помилкою (порядок у DOM) після того, як помилки відрисовані.
  useEffect(() => {
    if (!focusTick) return;
    const el = formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]');
    if (!el) return;
    el.focus({ preventScroll: true });
    el.scrollIntoView({ block: 'center' });
  }, [focusTick]);

  if (publicId) return <LeadSuccess publicId={publicId} onNew={onNew} newLabel={newLabel} settings={siteSettings} />;

  const partnerReady = !!consentText;
  const canSubmit = captcha.ready && partnerReady && partnerConsent && !submitting;
  // Чому кнопка неактивна (видимий текст, пов'язаний через aria-describedby).
  const blockedReason = submitting ? ''
    : !partnerReady ? 'Надсилання поки недоступне: немає даних партнера. Скористайтеся контактами вище.'
    : !partnerConsent ? 'Щоб надіслати, погодьтеся на передачу контактів партнеру.'
    : !captcha.ready ? 'Триває перевірка безпеки, зачекайте кілька секунд.'
    : '';
  const showErrors = (fields: Errors) => {
    if (DETAIL_FIELDS.some((f) => fields[f])) setMore(true);
    setErrors(fields);
    setFocusTick((t) => t + 1);
  };

  const trackStart = () => {
    if (startedRef.current) return;
    startedRef.current = true;
    sendMetric('lead_form_start');
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting || inFlightRef.current) return;
    const local: Errors = {};
    if (!name.trim()) local.name = "Вкажіть ім'я.";
    if (!phone.trim()) local.phone = 'Вкажіть телефон.';
    if (email.trim() && !EMAIL_RE.test(email.trim())) local.email = 'Вкажіть коректний email.';
    if (!consent) local.consent = 'Потрібна згода на обробку персональних даних.';
    setGeneral('');
    if (Object.keys(local).length) { showErrors(local); return; }
    setErrors({});

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

    inFlightRef.current = true;
    keyRef.current ??= newIdempotencyKey();
    setSubmitting(true);
    try {
      const created = await leadsApi.create(payload, keyRef.current);
      keyRef.current = null; // наступна відправка («Надіслати ще») - нова заявка з новим ключем
      startedRef.current = false;
      setPublicId(created.public_id);
      trackEvent('lead_submit', { source }); // лише категорія джерела, без ПДн
    } catch (err) {
      sendMetric('lead_submit_error'); // лише ключ: без статусу, тексту й ПДн
      if (err instanceof ApiError && err.status === 400) {
        if (isCaptchaFailed(err)) {
          setGeneral('Не вдалося пройти перевірку. Спробуйте ще раз.');
        } else {
          const parsed = parseFieldErrors(err.data);
          showErrors(parsed.fields);
          setGeneral(parsed.general.join(' ') || (Object.keys(parsed.fields).length ? '' : GENERAL_ERROR));
        }
      } else if (err instanceof ApiError && err.status === 429) {
        setGeneral('Забагато заявок, спробуйте пізніше.');
      } else if (err instanceof ApiError && err.status === 409) {
        keyRef.current = null; // ключ зайнятий іншими даними: наступна спроба - з новим
        setGeneral(err.message.startsWith('HTTP ') ? GENERAL_ERROR : err.message);
      } else if (err instanceof ApiError && err.status === 503) {
        setServerDown(true);
        setGeneral('');
      } else {
        setGeneral(GENERAL_ERROR);
      }
    } finally {
      inFlightRef.current = false;
      setSubmitting(false);
      captcha.bump(); // токен одноразовий: новий після кожної відповіді сервера
    }
  };

  return (
    <form ref={formRef} onSubmit={submit} onInput={trackStart} noValidate data-testid="lead-form"
      className="rounded-xl border bg-card p-5 text-card-foreground shadow-sm space-y-5 sm:p-6">
      <h3 className="text-xl font-bold tracking-tight text-foreground">Залишити заявку брокеру</h3>
      <p className="text-sm text-muted-foreground">Достатньо імені, телефону та згод: решту можна додати пізніше.</p>
      {vehicleLabel && landingSlug && (
        <p data-testid="lead-vehicle" className="text-sm text-foreground">
          Авто: <span className="font-semibold">{vehicleLabel}</span>
        </p>
      )}

      <div>
        <Label htmlFor="lead-name" className="mb-1.5">Ім&apos;я *</Label>
        <Input id="lead-name" name="name" required maxLength={100} autoComplete="name"
          value={name} aria-invalid={!!errors.name} aria-describedby={errors.name ? 'lead-name-err' : undefined}
          onChange={(e) => { touched.current.name = true; setName(e.target.value); }} />
        <FieldError id="lead-name-err" text={errors.name} />
      </div>

      <div>
        <Label htmlFor="lead-phone" className="mb-1.5">Телефон *</Label>
        <Input id="lead-phone" name="phone" type="tel" inputMode="tel" required maxLength={32}
          autoComplete="tel" placeholder="+380…"
          value={phone} aria-invalid={!!errors.phone} aria-describedby={errors.phone ? 'lead-phone-err' : undefined}
          onChange={(e) => { touched.current.phone = true; setPhone(e.target.value); }} />
        <FieldError id="lead-phone-err" text={errors.phone} />
      </div>

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium text-foreground">Зручний спосіб зв&apos;язку</legend>
        <div className="flex gap-4 flex-wrap">
          {METHODS.map((m) => (
            <label key={m.value} htmlFor={`lead-method-${m.value}`} className="flex min-h-11 items-center gap-2 text-sm text-foreground">
              <input id={`lead-method-${m.value}`} type="radio" className="size-5 accent-primary" name="contact_method" value={m.value}
                checked={method === m.value} onChange={() => setMethod(m.value)} />
              {m.label}
            </label>
          ))}
        </div>
        <FieldError id="lead-method-err" text={errors.contact_method} />
      </fieldset>

      {method !== 'phone' && (
        <div>
          <Label htmlFor="lead-handle" className="mb-1.5">
            Нік або контакт у {method === 'telegram' ? 'Telegram' : 'Viber'} (необов&apos;язково)
          </Label>
          <Input id="lead-handle" name="contact_handle" maxLength={64}
            aria-invalid={!!errors.contact_handle} aria-describedby={errors.contact_handle ? 'lead-handle-err' : undefined}
            value={handle} onChange={(e) => setHandle(e.target.value)} />
          <FieldError id="lead-handle-err" text={errors.contact_handle} />
        </div>
      )}

      <div>
        <Button type="button" variant="link" aria-expanded={more} aria-controls="lead-details" onClick={() => setMore((v) => !v)}
          className="h-auto px-0 underline">
          {more ? 'Сховати деталі' : "Додати деталі (необов'язково)"}
          <ChevronDown className={`transition-transform ${more ? 'rotate-180' : ''}`} strokeWidth={ICON_STROKE} aria-hidden="true" />
        </Button>
        <div id="lead-details" hidden={!more} className="mt-3 space-y-3">
          <div>
            <Label htmlFor="lead-email" className="mb-1.5">Email (необов&apos;язково)</Label>
            <Input id="lead-email" name="email" type="email" inputMode="email" maxLength={254} autoComplete="email"
              value={email} aria-invalid={!!errors.email}
              aria-describedby={errors.email ? 'lead-email-hint lead-email-err' : 'lead-email-hint'}
              onChange={(e) => setEmail(e.target.value)} />
            <p id="lead-email-hint" className="text-sm text-muted-foreground mt-1">
              На нього надійде копія розрахунку та статуси заявки.
            </p>
            <FieldError id="lead-email-err" text={errors.email} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <Label htmlFor="lead-budget" className="mb-1.5">Бюджет під ключ ($)</Label>
              <Input id="lead-budget" name="budget_usd" inputMode="decimal"
                value={budget} aria-invalid={!!errors.budget_usd} aria-describedby={errors.budget_usd ? 'lead-budget-err' : undefined}
                onChange={(e) => setBudget(e.target.value)} />
              <FieldError id="lead-budget-err" text={errors.budget_usd} />
            </div>
            <div>
              <Label htmlFor="lead-needed" className="mb-1.5">Коли потрібне авто</Label>
              <select id="lead-needed" name="needed_when" className={FIELD_CLASS} value={needed}
                aria-invalid={!!errors.needed_when} aria-describedby={errors.needed_when ? 'lead-needed-err' : undefined}
                onChange={(e) => setNeeded(e.target.value as LeadNeededWhen | '')}>
                <option value="">Не вказано</option>
                {NEEDED.map((n) => <option key={n.value} value={n.value}>{n.label}</option>)}
              </select>
              <FieldError id="lead-needed-err" text={errors.needed_when} />
            </div>
            <div>
              <Label htmlFor="lead-city" className="mb-1.5">Місто</Label>
              <Input id="lead-city" name="city" maxLength={100} autoComplete="address-level2"
                value={city} aria-invalid={!!errors.city} aria-describedby={errors.city ? 'lead-city-err' : undefined}
                onChange={(e) => setCity(e.target.value)} />
              <FieldError id="lead-city-err" text={errors.city} />
            </div>
          </div>
          <div>
            <Label htmlFor="lead-comment" className="mb-1.5">Коментар</Label>
            <Textarea id="lead-comment" name="comment" rows={3} maxLength={1000}
              value={comment} aria-invalid={!!errors.comment} aria-describedby={errors.comment ? 'lead-comment-err' : undefined}
              onChange={(e) => setComment(e.target.value)} />
            <FieldError id="lead-comment-err" text={errors.comment} />
          </div>
        </div>
      </div>

      <div>
        <label htmlFor="lead-consent" className="flex items-start gap-2.5 text-sm text-foreground">
          <input id="lead-consent" name="consent" type="checkbox" className="mt-0.5 size-5 shrink-0 accent-primary" checked={consent}
            aria-invalid={!!errors.consent} aria-describedby={errors.consent ? 'lead-consent-err' : undefined}
            onChange={(e) => setConsent(e.target.checked)} />
          <span>
            Погоджуюсь на обробку персональних даних відповідно до{' '}
            <Link href="/privacy" target="_blank" className="text-primary underline underline-offset-4">політики конфіденційності</Link>
          </span>
        </label>
        <FieldError id="lead-consent-err" text={errors.consent} />
      </div>

      <div>
        <label htmlFor="lead-partner-consent" className="flex items-start gap-2.5 text-sm text-foreground">
          <input id="lead-partner-consent" name="partner_consent" type="checkbox" className="mt-0.5 size-5 shrink-0 accent-primary"
            checked={partnerConsent} disabled={!partnerReady}
            aria-invalid={!!errors.partner_consent} aria-describedby={errors.partner_consent ? 'lead-partner-err' : undefined}
            onChange={(e) => setPartnerConsent(e.target.checked)} />
          <span data-testid="partner-consent-text">{consentText || 'Згода на передачу контактів партнеру'}</span>
        </label>
        {(consentText === '' || serverDown) && (
          <div role="alert" data-testid="lead-unavailable"
            className="mt-2 rounded-lg border border-warning bg-warning/15 p-3 text-sm text-foreground">
            <p className="flex items-center gap-2 font-semibold">
              <TriangleAlert className="size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
              Заявки онлайн тимчасово недоступні
            </p>
            <FallbackContact settings={siteSettings} onRetry={retry} retrying={retrying} />
          </div>
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
        <p role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden="true" />
          <span>{general}</span>
        </p>
      )}

      {siteSettings?.partner_name?.trim() && (
        <div data-testid="lead-partner-info" className="rounded-lg border bg-muted p-3 text-sm text-foreground">
          <p>Заявку обробляє партнер: <span className="font-semibold">{siteSettings.partner_name.trim()}</span></p>
          <ContactList settings={siteSettings} title="Контакти:" />
        </div>
      )}

      <Button type="submit" size="lg" disabled={!canSubmit} aria-describedby={blockedReason ? 'lead-submit-hint' : undefined}
        className="w-full text-base font-bold">
        <Send strokeWidth={ICON_STROKE} aria-hidden="true" />
        {submitting ? 'Надсилаю…' : 'Надіслати'}
      </Button>
      {blockedReason && (
        <p id="lead-submit-hint" data-testid="lead-submit-hint" className="text-sm text-muted-foreground -mt-2">{blockedReason}</p>
      )}
    </form>
  );
}
