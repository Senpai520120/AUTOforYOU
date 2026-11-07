'use client';
/**
 * Капча (задача 1.6, Н-33). Єдиний компонент для всіх точок Q2.
 *
 * - provider=turnstile: скрипт Cloudflare вантажиться лише тут, малюється віджет;
 * - provider=honeypot: тільки приховане поле `website`; токен форми віддається після
 *   мінімального часу заповнення (інакше сервер відхилить «надто швидку» форму);
 * - provider=off: токен '' (форма може відправлятися);
 * - `onToken(null)` — токена немає/протух (кнопка відправки неактивна);
 * - зміна `resetKey` скидає віджет: після КОЖНОЇ відповіді сервера форма робить resetKey++.
 */
import { useEffect, useRef, useState } from 'react';
import { apiGet } from '@/api/client';
import type { AuthConfig, CaptchaConfig } from '@/lib/captcha';

const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
// Трохи більше за CAPTCHA_MIN_FILL_SECONDS=3 на сервері.
const HONEYPOT_DELAY_MS = 3200;
export const CAPTCHA_LOAD_ERROR =
  'Не вдалося завантажити перевірку. Вимкніть блокувальник або спробуйте пізніше';

interface TurnstileApi {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id?: string) => void;
  remove: (id?: string) => void;
}
declare global {
  interface Window { turnstile?: TurnstileApi }
}

let scriptPromise: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (!scriptPromise) {
    scriptPromise = new Promise<TurnstileApi>((resolve, reject) => {
      const s = document.createElement('script');
      s.src = SCRIPT_SRC;
      s.async = true;
      s.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error('no turnstile')));
      s.onerror = () => reject(new Error('script blocked'));
      document.head.appendChild(s);
    }).catch((e) => {
      scriptPromise = null; // дозволити повторну спробу при наступному монтуванні
      document.querySelector(`script[src="${SCRIPT_SRC}"]`)?.remove();
      throw e;
    });
  }
  return scriptPromise;
}

interface Props {
  config: CaptchaConfig | null;
  onToken: (token: string | null) => void;
  resetKey?: number;
  onHoneypot?: (value: string) => void;
}

export default function Captcha({ config, onToken, resetKey = 0, onHoneypot }: Props) {
  const provider = config?.provider;
  if (provider === 'turnstile') {
    return <TurnstileWidget siteKey={config!.site_key} onToken={onToken} resetKey={resetKey} />;
  }
  if (provider === 'honeypot') {
    return <Honeypot initialToken={config!.form_token ?? ''} onToken={onToken} onHoneypot={onHoneypot} resetKey={resetKey} />;
  }
  return <Off active={provider === 'off'} onToken={onToken} />;
}

function Off({ active, onToken }: { active: boolean; onToken: (t: string | null) => void }) {
  useEffect(() => { onToken(active ? '' : null); }, [active, onToken]);
  return null;
}

function Honeypot({ initialToken, onToken, onHoneypot, resetKey }: {
  initialToken: string; onToken: (t: string | null) => void; onHoneypot?: (v: string) => void; resetKey: number;
}) {
  // form_token одноразовый: после каждой відповіді сервера (resetKey++) беремо НОВИЙ з /auth/config/.
  const [formToken, setFormToken] = useState(initialToken);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    let alive = true;
    onToken(null);
    apiGet<AuthConfig>('/api/v1/auth/config/')
      .then((c) => { if (alive) setFormToken(c.captcha.form_token ?? ''); })
      .catch(() => { /* токен лишається null: кнопка неактивна */ });
    return () => { alive = false; };
  }, [resetKey, onToken]);
  useEffect(() => {
    onToken(null);
    const t = window.setTimeout(() => onToken(formToken), HONEYPOT_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [formToken, onToken]);
  return (
    <div aria-hidden="true" style={{ position: 'absolute', left: '-10000px', width: 1, height: 1, overflow: 'hidden' }}>
      <input type="text" name="website" tabIndex={-1} autoComplete="off" defaultValue=""
        onChange={(e) => onHoneypot?.(e.target.value)} />
    </div>
  );
}

function TurnstileWidget({ siteKey, onToken, resetKey }: {
  siteKey: string; onToken: (t: string | null) => void; resetKey: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const [failed, setFailed] = useState(false);
  const firstReset = useRef(true);
  const onTokenRef = useRef(onToken);
  useEffect(() => { onTokenRef.current = onToken; }, [onToken]);

  useEffect(() => {
    let alive = true;
    onTokenRef.current(null);
    loadTurnstile()
      .then((api) => {
        if (!alive || !box.current) return;
        widgetId.current = api.render(box.current, {
          sitekey: siteKey,
          callback: (t: string) => onTokenRef.current(t),
          'expired-callback': () => onTokenRef.current(null),
          'error-callback': () => onTokenRef.current(null),
        });
      })
      .catch(() => { if (alive) { setFailed(true); onTokenRef.current(null); } });
    return () => {
      alive = false;
      if (widgetId.current && window.turnstile) window.turnstile.remove(widgetId.current);
      widgetId.current = null;
    };
  }, [siteKey]);

  useEffect(() => {
    if (firstReset.current) { firstReset.current = false; return; }
    onTokenRef.current(null);
    if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current);
  }, [resetKey]);

  return (
    <div>
      <div ref={box} data-testid="captcha-widget" />
      {failed && <p role="alert" className="text-red-600 text-sm">{CAPTCHA_LOAD_ERROR}</p>}
    </div>
  );
}
