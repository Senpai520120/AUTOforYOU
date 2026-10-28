"""Готовность к запуску: единое место правды для `manage.py launch_check` и теста полноты шаблонов (задача 7.7a).

- `REQUIRED_VARS` - обязательные для прода переменные (группа -> список). Их использует и `launch_check`, и
  тест `core/tests_env_templates.py` (каждая есть в `.env.example` и в `docs/LAUNCH_CHECKLIST.md`).
- `PROD_TEMPLATE_VALUES` / `DEV_TEMPLATE_VALUES` - значения, которые должны стоять в шаблонах `.env`.
- `run_checks(wave, ...)` - только чтение: ни одной записи в БД и ни одного сетевого вызова.
  Секреты не печатаются: только «задано / не задано».

Режим `wave=1` (ВОЛНА-1) - единственный в 7.7a; режим ВОЛНЫ-2 - задача 7.7b.
"""
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from core.c2c import c2c_enabled, c2c_public_posting_enabled, payments_enabled
from core.secret_key import MIN_PROD_KEY_LENGTH, PLACEHOLDER_MARKERS
from integrations.base import MODE_DEMO, is_placeholder

ERROR = 'error'
WARNING = 'warning'
OK = 'ok'
INFO = 'info'

# Источник значения: 'settings' - Django settings (в тестах подменяется override_settings),
# 'env' - os.environ (переменные, которые Django-settings не хранит: читают nginx, backup, Sentry).
SETTINGS = 'settings'
ENV = 'env'

# Обязательные для прода: группа -> [(имя, источник, что это)]. Пустое значение или заглушка = ошибка.
REQUIRED_VARS = {
    'Django і безпека': [
        ('SECRET_KEY', SETTINGS, 'секретний ключ Django (не коротше 50 символів, без заглушок)'),
        ('ALLOWED_HOSTS', SETTINGS, 'домен сайту'),
        ('CORS_ALLOWED_ORIGINS', SETTINGS, 'origin сайту для API'),
        ('CSRF_TRUSTED_ORIGINS', SETTINGS, 'origin для POST з cookie-сесією'),
    ],
    'Домен і HTTPS': [
        ('DOMAIN', ENV, 'домен сайту без http/https'),
        ('SITE_URL', SETTINGS, 'повна адреса сайту (https://домен)'),
    ],
    'БД і Redis': [
        ('DATABASE_URL', ENV, 'адреса PostgreSQL'),
        ('POSTGRES_PASSWORD', ENV, 'пароль PostgreSQL'),
        ('REDIS_URL', ENV, 'адреса Redis'),
        ('REDIS_PASSWORD', ENV, 'пароль Redis'),
    ],
    'Пошта': [
        ('EMAIL_HOST', SETTINGS, 'SMTP-сервер'),
        ('EMAIL_HOST_USER', SETTINGS, 'користувач SMTP'),
        ('EMAIL_HOST_PASSWORD', SETTINGS, 'пароль SMTP'),
        ('DEFAULT_FROM_EMAIL', SETTINGS, 'адреса відправника на вашому домені'),
    ],
    'Моніторинг': [
        ('SENTRY_DSN', ENV, 'Sentry/GlitchTip DSN'),
    ],
    'Резервні копії поза сервером': [
        ('BACKUP_S3_BUCKET', ENV, 'bucket R2/S3 для бекапів'),
        ('BACKUP_S3_ENDPOINT_URL', ENV, 'endpoint R2/S3'),
        ('BACKUP_S3_ACCESS_KEY_ID', ENV, 'ключ доступу до bucket бекапів'),
        ('BACKUP_S3_SECRET_ACCESS_KEY', ENV, 'секрет доступу до bucket бекапів'),
        ('BACKUP_ENCRYPTION_PASSPHRASE', ENV, 'пароль шифрування бекапів (gpg)'),
    ],
}

# Значення за замовчуванням у шаблонах .env (перевіряє тест полноты шаблонів).
PROD_TEMPLATE_VALUES = dict(
    ANTISPAM_MODE='hard', PAYMENTS_ENABLED='false', C2C_ENABLED='false', C2C_PUBLIC_POSTING_ENABLED='false',
    DEBUG='false', TURNSTILE_SECRET_KEY='',
)
DEV_TEMPLATE_VALUES = dict(ANTISPAM_MODE='soft', C2C_ENABLED='true', PAYMENTS_ENABLED='false')

# Замороженные на ВОЛНЕ-1 модули: флаг settings -> имя переменной (2.8, 3.2a, Q7).
FROZEN_MODULE_FLAGS = (
    'LOTS_ENABLED', 'B2B_ENABLED', 'DEALERS_ENABLED', 'SHIPMENTS_ENABLED', 'VIN_REPORTS_ENABLED',
    'LEGACY_CARS_API_ENABLED',
)

# Метка свежего бэкапа старше этого - предупреждение (healthcheck сервиса backup использует те же 26 часов).
BACKUP_STALE_HOURS = 26
# Метрики 8.7 без записей дольше этого - предупреждение, что запись счётчиков не работает.
METRICS_STALE_DAYS = 3

# Интеграции, «вимкнено» которых допустимо на запуске (аналитика выключена до заведения ID; платежи и
# замороженные модули - по своим флагам). Остальные не настроенные - предупреждение.
OPTIONAL_PROVIDERS = {'ga4', 'cloudflare_analytics'}


@dataclass
class Finding:
    level: str
    text: str


def _value(name: str, source: str) -> str:
    if source == ENV:
        return str(os.environ.get(name, '') or '').strip()
    raw = getattr(settings, name, '')
    if isinstance(raw, (list, tuple)):
        raw = ','.join(str(x) for x in raw)
    return str(raw or '').strip()


def _is_filled(name: str, value: str) -> bool:
    if is_placeholder(value) or '<' in value or '>' in value:
        return False
    if name == 'SECRET_KEY':
        low = value.lower()
        return len(value) >= MIN_PROD_KEY_LENGTH and not any(m.lower() in low for m in PLACEHOLDER_MARKERS)
    return True


def required_var_names() -> list:
    return [name for items in REQUIRED_VARS.values() for name, _src, _hint in items]


def _flag(name: str) -> bool:
    return bool(getattr(settings, name, False))


# ─── Проверки ────────────────────────────────────────────────────────────────

def check_required_vars() -> list:
    findings = []
    for group, items in REQUIRED_VARS.items():
        for name, source, hint in items:
            value = _value(name, source)
            if name == 'ALLOWED_HOSTS' and not settings.DEBUG:
                hosts = [h for h in value.split(',') if h]
                if hosts and all(h.lstrip('.') in ('localhost', '127.0.0.1', '0.0.0.0', 'backend') for h in hosts):
                    findings.append(Finding(ERROR, f'{name}: лише localhost-хости, потрібен домен сайту ({group})'))
                    continue
            if _is_filled(name, value):
                findings.append(Finding(OK, f'{name}: задано'))
            elif value:
                findings.append(Finding(ERROR, f'{name}: заглушка або слабке значення - {hint} ({group})'))
            else:
                findings.append(Finding(ERROR, f'{name}: не задано - {hint} ({group})'))
    return findings


def check_flags() -> list:
    """Флаги ВОЛНЫ-1: платежи и публичная подача закрыты, замороженные модули выключены, антиспам жёсткий."""
    findings = []
    prod = not settings.DEBUG
    if settings.DEBUG:
        findings.append(Finding(WARNING, 'DEBUG=true: режим розробки, прод-перевірки прапорців пом\'якшено'))
    posting = c2c_public_posting_enabled()
    if posting and prod:
        findings.append(Finding(ERROR, 'C2C_PUBLIC_POSTING_ENABLED=true: публічна подача оголошень не повинна '
                                       'бути відкрита на ВОЛНІ-1 (режим «засів»: false)'))
    else:
        findings.append(Finding(OK, f'C2C_PUBLIC_POSTING_ENABLED={str(posting).lower()}'))
    if c2c_enabled():
        findings.append(Finding(INFO, 'C2C_ENABLED=true: розділ видно (режим «засів»)'))
    else:
        findings.append(Finding(OK, 'C2C_ENABLED=false: розділ «Оголошення по Україні» вимкнено'))
    if payments_enabled() and prod:
        findings.append(Finding(ERROR, 'PAYMENTS_ENABLED=true: платежі на ВОЛНІ-1 мають бути вимкнені '
                                       '(умови увімкнення - docs/LAUNCH_CHECKLIST.md)'))
    elif payments_enabled():
        findings.append(Finding(WARNING, 'PAYMENTS_ENABLED=true (режим розробки)'))
    else:
        findings.append(Finding(OK, 'PAYMENTS_ENABLED=false'))
    for name in FROZEN_MODULE_FLAGS:
        if _flag(name):
            findings.append(Finding(WARNING, f'{name}=true: модуль заморожено на ВОЛНІ-1, тримайте false'))
    mode = str(getattr(settings, 'ANTISPAM_MODE', '') or '').strip().lower()
    if mode == 'hard':
        findings.append(Finding(OK, 'ANTISPAM_MODE=hard'))
    elif prod:
        findings.append(Finding(ERROR, f'ANTISPAM_MODE={mode or "(порожньо)"}: у проді має бути hard'))
    else:
        findings.append(Finding(INFO, f'ANTISPAM_MODE={mode} (режим розробки)'))
    return findings


def check_captcha() -> list:
    findings = []
    provider = str(getattr(settings, 'CAPTCHA_PROVIDER', '') or '').strip().lower()
    secret = _value('TURNSTILE_SECRET_KEY', SETTINGS)
    if provider == 'off' and not settings.DEBUG:
        findings.append(Finding(ERROR, 'CAPTCHA_PROVIDER=off при DEBUG=false: захист форм вимкнено повністю'))
    elif provider != 'turnstile' or not secret:
        findings.append(Finding(
            WARNING, 'TURNSTILE_SECRET_KEY не задано або CAPTCHA_PROVIDER не turnstile: капча - тільки honeypot '
                     'і ліміт за IP (прийнятно на запуску, див. чек-лист)',
        ))
    else:
        findings.append(Finding(OK, 'Капча Turnstile: ключ задано'))
    return findings


def check_integrations() -> list:
    """Статусы интеграций из реестра 3.1 (без БД и без сети)."""
    from integrations.registry import get_statuses

    findings = []
    payments_on = payments_enabled()
    for status in get_statuses(with_health=False):
        label = f'{status.title} ({status.key}): режим {status.mode_label}'
        if status.key in OPTIONAL_PROVIDERS:
            findings.append(Finding(INFO, f'{label}, {"налаштовано" if status.configured else "вимкнено"}'))
        elif status.key == 'liqpay' and not payments_on:
            findings.append(Finding(INFO, f'{label} - платежі вимкнено прапорцем PAYMENTS_ENABLED=false'))
        elif status.key in ('vin_report', 'opendatabot') and not _flag('VIN_REPORTS_ENABLED'):
            findings.append(Finding(INFO, f'{label} - модуль заморожено'))
        elif status.key == 'lots' and not _flag('LOTS_ENABLED'):
            findings.append(Finding(INFO, f'{label} - модуль лотів заморожено'))
        elif status.configured and status.mode != MODE_DEMO:
            findings.append(Finding(OK, f'{label}, налаштовано'))
        else:
            findings.append(Finding(WARNING, f'{label}, не налаштовано: {status.reason or "немає ключів"}'))
    return findings


def check_carvertical_url() -> list:
    if _value('CARVERTICAL_PARTNER_URL', SETTINGS):
        return [Finding(OK, 'CARVERTICAL_PARTNER_URL: задано')]
    return [Finding(WARNING, 'партнерське посилання carVertical не задано, блок не показується (CARVERTICAL_PARTNER_URL)')]


def check_site_settings() -> list:
    from site_settings.models import SiteSettings

    findings = []
    obj = SiteSettings.objects.filter(pk=1).first()  # load() создаёт запись - здесь нельзя
    if obj is None:
        return [Finding(ERROR, 'Налаштування сайту (адмінка) ще не створені: реквізити, контакти, партнер, документи')]
    missing = [label for label, value in (
        ('правова форма', obj.owner_legal_form), ('юридична назва', obj.owner_legal_name),
        ('ЄДРПОУ/РНОКПП', obj.owner_code), ('адреса власника', obj.owner_address),
        ('email підтримки', obj.support_email), ('email для звернень щодо ПДн', obj.privacy_email),
        ('телефон', obj.phone),
    ) if not str(value or '').strip()]
    if missing:
        findings.append(Finding(ERROR, 'Налаштування сайту: не заповнено реквізити/контакти: ' + ', '.join(missing)))
    else:
        findings.append(Finding(OK, 'Налаштування сайту: реквізити й контакти заповнені'))
    if not (obj.partner_name or '').strip():
        findings.append(Finding(ERROR, 'назва партнера не заповнена: чекбокс згоди на передачу контактів неактивний'))
    else:
        findings.append(Finding(OK, 'Назва партнера задана'))
    if not (obj.legal_docs_version or '').strip():
        findings.append(Finding(ERROR, 'версія юридичних документів не задана (Налаштування сайту -> Версія документів)'))
    else:
        findings.append(Finding(OK, f'Версія юридичних документів: {obj.legal_docs_version}'))
    if not obj.legal_docs_approved:
        findings.append(Finding(WARNING, 'юридичні документи не відмічені як перевірені юристом (на сторінках плашка «Шаблон»)'))
    if obj.data_retention_years is None:
        findings.append(Finding(WARNING, 'строк зберігання платіжних документів не заданий (чекає відповіді бухгалтера)'))
    return findings


def _active(qs, today):
    from django.db.models import Q

    return qs.filter(valid_from__lte=today).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))


def check_tariffs() -> list:
    """Активные тарифы есть (ошибка, если нет); неподтверждённые - предупреждение, при PAYMENTS_ENABLED - ошибка.

    `payments.services.unconfirmed_tariffs()` (задача 4.1) пока не существует: вместо неё используются
    признаки подтверждения самих тарифов (`is_verified`, `CustomsCalcRule.confirmed_by_broker`).
    """
    from pricing.models import (
        AuctionFeeTier,
        AuctionFixedFee,
        BrokerServiceFee,
        CustomsCalcRule,
        CustomsExciseRate,
        EuToUaDeliveryRate,
        ExchangeRate,
        OceanFreightRate,
        PensionFundBracket,
        UaDeliveryRate,
        UsLandRoute,
    )

    today = timezone.localdate()
    required = (
        (AuctionFeeTier, 'аукціонні збори'), (AuctionFixedFee, 'фіксовані збори аукціону'),
        (UsLandRoute, 'доставка по США'), (OceanFreightRate, 'морський фрахт'),
        (EuToUaDeliveryRate, 'доставка ЄС-Україна'), (CustomsExciseRate, 'акциз'),
        (PensionFundBracket, 'пенсійний збір'),
    )
    optional = ((UaDeliveryRate, 'доставка по Україні'), (BrokerServiceFee, 'послуги брокера'),
                (CustomsCalcRule, 'правило розмитнення'))
    findings = []
    unconfirmed = []
    for model, title in required + optional:
        rows = _active(model.objects.all(), today)
        total = rows.count()
        if total == 0:
            level = ERROR if (model, title) in required else WARNING
            findings.append(Finding(level, f'Тарифи: немає активних записів «{title}» ({model.__name__}, адмінка «Тарифи»)'))
            continue
        findings.append(Finding(OK, f'Тарифи «{title}»: активних записів {total}'))
        if model is CustomsCalcRule:
            if rows.filter(confirmed_by_broker=False).exists():
                unconfirmed.append(f'{title} (не звірено з брокером)')
        elif rows.filter(is_verified=False).exists():
            unconfirmed.append(title)
    if not ExchangeRate.objects.exists():
        findings.append(Finding(ERROR, 'Курси валют: немає жодного курсу (ExchangeRate)'))
    else:
        findings.append(Finding(OK, 'Курси валют: є'))
    if unconfirmed:
        level = ERROR if payments_enabled() else WARNING
        findings.append(Finding(
            level, 'Тарифи не підтверджені власником/брокером, розрахунок лишається орієнтовним: ' + '; '.join(unconfirmed)))
    else:
        findings.append(Finding(OK, 'Усі активні тарифи підтверджені'))
    return findings


def check_roles() -> list:
    from users.models import CustomUser

    findings = []
    for role, title in ((CustomUser.Role.BROKER, 'брокер'), (CustomUser.Role.MODERATOR, 'модератор')):
        if CustomUser.objects.filter(role=role, is_active=True).exists():
            findings.append(Finding(OK, f'Є користувач з роллю {title}'))
        else:
            findings.append(Finding(WARNING, f'Немає користувача з роллю {title} (призначається в адмінці користувачів)'))
    return findings


def check_lead_notifications() -> list:
    from leads.models import LeadNotificationSettings

    row = LeadNotificationSettings.objects.filter(pk=1).first()
    chat = (row.telegram_chat_id if row else '') or _value('TELEGRAM_BROKER_CHAT_ID', SETTINGS)
    emails = (row.broker_emails if row else '') or _value('BROKER_NOTIFY_EMAIL', SETTINGS)
    findings = []
    if str(chat).strip():
        findings.append(Finding(OK, 'Telegram chat_id брокера для заявок: задано'))
    else:
        findings.append(Finding(ERROR, 'TELEGRAM_BROKER_CHAT_ID не задано (і порожньо в «Налаштування сповіщень про '
                                       'заявки»): заявки нікуди не прийдуть'))
    if str(emails).strip():
        findings.append(Finding(OK, 'Резервний email брокера: задано'))
    else:
        findings.append(Finding(ERROR, 'Резервний email брокера не задано (BROKER_NOTIFY_EMAIL або «Налаштування '
                                       'сповіщень про заявки»): заявки без запасного каналу'))
    return findings


def check_photo_mode() -> list:
    hosts = getattr(settings, 'LOT_PHOTO_ALLOWED_HOSTS', [])
    if hosts:
        return [Finding(WARNING, 'Режим фото лотів: on (LOT_PHOTO_ALLOWED_HOSTS задано); на запуску має бути off (Q8)')]
    return [Finding(OK, 'Режим фото лотів: off (LOT_PHOTO_ALLOWED_HOSTS порожній)')]


def check_backup_mark(now: datetime | None = None) -> list:
    """Метка `.last_success` лежит в BACKUP_DIR на хосте; из контейнера backend её обычно не видно."""
    directory = os.environ.get('BACKUP_DIR', '').strip()
    mark = Path(directory) / '.last_success' if directory else None
    if mark is None or not mark.is_file():
        return [Finding(INFO, 'Мітка останнього бекапу (.last_success) недоступна з цього контейнера: перевіряйте '
                              'на хості (`ls -l backups/.last_success`), тут перевірено лише змінні')]
    now = now or timezone.now()
    age = now - datetime.fromtimestamp(mark.stat().st_mtime, tz=now.tzinfo)
    if age > timedelta(hours=BACKUP_STALE_HOURS):
        return [Finding(WARNING, f'Останній успішний бекап старший за {BACKUP_STALE_HOURS} год')]
    return [Finding(OK, 'Останній успішний бекап свіжий')]


def check_metrics_and_tasks() -> list:
    from metrics.models import DailyMetric
    from task_ledger.models import FailedTask

    findings = []
    last = DailyMetric.objects.order_by('-date').values_list('date', flat=True).first()
    if last is None:
        findings.append(Finding(WARNING, 'Лічильники (8.7): записів ще немає, перевірте запис після першого візиту'))
    elif (timezone.localdate() - last).days > METRICS_STALE_DAYS:
        findings.append(Finding(WARNING, f'Лічильники (8.7): останній запис {last}, запис, схоже, не працює'))
    else:
        findings.append(Finding(OK, f'Лічильники (8.7): останній запис {last}'))
    failed = FailedTask.objects.count()
    findings.append(Finding(INFO, f'Невдалі Celery-завдання (8.9) у журналі: {failed}'))
    return findings


def check_seeding(threshold: int | None) -> list:
    """При C2C_ENABLED=true: достаточно ли объявлений в разделе. Порог - аргумент или C2C_SEED_THRESHOLD."""
    if not c2c_enabled():
        return []
    from local_listings.models import LocalListing

    if threshold is None:
        raw = os.environ.get('C2C_SEED_THRESHOLD', '').strip()
        threshold = int(raw) if raw.isdigit() else None
    if threshold is None:
        return [Finding(INFO, 'Поріг «засіву» не задано (C2C_SEED_THRESHOLD або --seed-threshold): перевірку пропущено')]
    count = LocalListing.objects.filter(status=LocalListing.Status.ACTIVE).count()
    if count < threshold:
        return [Finding(WARNING, f'Розділ оголошень увімкнено, але активних оголошень {count} - менше порога засіву {threshold}')]
    return [Finding(OK, f'Активних оголошень {count} (поріг засіву {threshold})')]


def run_checks(wave: int = 1, seed_threshold: int | None = None) -> list:
    """Все проверки режима ВОЛНЫ-1. Только чтение."""
    if wave != 1:
        raise ValueError('режим 2 - задача 7.7b')
    findings = []
    for check in (
        check_required_vars, check_flags, check_captcha, check_integrations, check_carvertical_url,
        check_site_settings, check_tariffs, check_roles, check_lead_notifications, check_photo_mode,
        check_backup_mark, check_metrics_and_tasks,
    ):
        findings.extend(check())
    findings.extend(check_seeding(seed_threshold))
    return findings
