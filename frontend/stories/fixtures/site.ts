/** Мок мережі для форм: усі запити до API у stories відповідають фейковими даними. */
const SITE_SETTINGS = {
  owner_legal_name: 'Тестовий власник',
  support_email: 'support@example.test',
  phone: '+380000000000',
  manager_contact: 'Тестовий менеджер',
  partner_consent_text: '',
  lead_response_hours: 24,
  lead_next_steps: '',
  owner_configured: true,
};
const AUTH_CONFIG = {
  captcha: { provider: 'off', site_key: '', login_after_failures: 3, on_login: false },
  email_verification_required: false,
};

/** Підміняє window.fetch на фейковий; повертає функцію відновлення. */
export function installFakeFetch(): () => void {
  const original = window.fetch;
  window.fetch = async (input: RequestInfo | URL) => {
    const url = String(input instanceof Request ? input.url : input);
    const body = url.includes('site-settings') ? SITE_SETTINGS : url.includes('auth/config') ? AUTH_CONFIG : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  return () => {
    window.fetch = original;
  };
}
