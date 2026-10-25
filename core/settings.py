import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root (next to manage.py).
# encoding='utf-8' is explicit — avoids any system-locale surprises on Windows.
load_dotenv(BASE_DIR / '.env', encoding='utf-8', override=False)

# ─── Безопасность ─────────────────────────────────────────────────────────────
# DEBUG=False по умолчанию; для локальной разработки добавить DEBUG=true в .env
DEBUG = os.environ.get('DEBUG', 'false').lower() in ('true', '1', 'yes')

# Флаг тест-раннера: единственный, вычисляется один раз (см. блок изоляции в конце файла).
_TESTING = 'test' in sys.argv

# In production set: ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
_raw_hosts = os.environ.get('ALLOWED_HOSTS', '')
_explicit_hosts = [h.strip() for h in _raw_hosts.split(',') if h.strip()]
if _explicit_hosts:
    ALLOWED_HOSTS = _explicit_hosts
elif DEBUG:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']
elif _TESTING:
    ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
else:
    # 01-Q9: без ALLOWED_HOSTS прод отвечал бы 400 на каждый запрос - лучше не стартовать.
    raise ImproperlyConfigured('ALLOWED_HOSTS не задан. Укажите домен сайта в .env: ALLOWED_HOSTS=домен,www.домен')

# ─── SECRET_KEY и DEBUG (задача 7.2, 01-S10, 01-C8) ────────────────────────────
from core.secret_key import check_debug_hosts, resolve_secret_key  # noqa: E402

SECRET_KEY = resolve_secret_key(os.environ, debug=DEBUG, testing=_TESTING, base_dir=BASE_DIR)
check_debug_hosts(os.environ, debug=DEBUG, allowed_hosts=ALLOWED_HOSTS)

# ─── Приложения ───────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'storages',

    'users',
    'vehicles',
    'pricing',
    'listings',
    'local_listings',
    'shipments',
    'integrations',
    'payments',
    'cars',
    'telegram_bot',
    'messaging',
    'notifications',
    'favorites',
    'saved_searches',
    'reports',
    'deals',
    'site_settings',
    'leads',
    'task_ledger',
    'metrics',
    # Проект, не приложение: подключён только ради management-команд (monitoring_test, 7.6). Моделей нет.
    'core',

    'drf_spectacular',
    'django_celery_beat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'core.middleware.ModuleFlagMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ─── База данных ──────────────────────────────────────────────────────────────
# Не задан DATABASE_URL → SQLite (локальная разработка, работает без настройки).
# Задан DATABASE_URL → PostgreSQL (или любой другой провайдер).
# Пример для Postgres: DATABASE_URL=postgres://user:pass@localhost:5432/autoforyou
_DATABASE_URL = os.environ.get('DATABASE_URL', '')
if _DATABASE_URL:
    DATABASES = {'default': dj_database_url.parse(_DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'users.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Kyiv'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Кэш ──────────────────────────────────────────────────────────────────────
# Не задан REDIS_URL → LocMemCache (dev, в памяти процесса, без Redis).
# Задан REDIS_URL → django-redis (prod / staging).
_REDIS_URL = os.environ.get('REDIS_URL', '')
CACHES = {
    'default': (
        {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': _REDIS_URL,
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
            'KEY_PREFIX': 'aut',
        }
        if _REDIS_URL else
        {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
    )
}

# ─── Медиафайлы и хранилище (задача 7.2) ───────────────────────────────────────
# STORAGES вместо удалённых в Django 5.1 DEFAULT_FILE_STORAGE/STATICFILES_STORAGE (01-C1).
# Без S3-переменных - локально; S3_BUCKET_NAME + ключи - медиа в S3/R2, статика локальная.
from core.storage_settings import build_storage_settings  # noqa: E402

globals().update(build_storage_settings(os.environ, BASE_DIR))

# ─── Безопасная загрузка изображений (задача 1.10, core/uploads.py) ────────────
# Тип определяется по содержимому; файл пересохраняется без EXIF/GPS с uuid-именем.
UPLOAD_IMAGE_MAX_SIZE_MB = int(os.environ.get('UPLOAD_IMAGE_MAX_SIZE_MB', '8'))
# Защита от decompression bomb: ширина × высота.
UPLOAD_IMAGE_MAX_PIXELS = int(os.environ.get('UPLOAD_IMAGE_MAX_PIXELS', '25000000'))
# Только из JPEG, PNG, WEBP (другие форматы сервис не пересохраняет и игнорирует).
UPLOAD_IMAGE_ALLOWED_FORMATS = [
    f.strip().upper() for f in os.environ.get('UPLOAD_IMAGE_ALLOWED_FORMATS', 'JPEG,PNG,WEBP').split(',')
    if f.strip()
]
UPLOAD_IMAGE_JPEG_QUALITY = int(os.environ.get('UPLOAD_IMAGE_JPEG_QUALITY', '85'))
# Хосты, с которых upload_lot_photos может качать фото лотов (и редиректы). Пусто — перенос выключен.
# `*.example.com` — любой поддомен example.com.
LOT_PHOTO_ALLOWED_HOSTS = [
    h.strip().lower() for h in os.environ.get('LOT_PHOTO_ALLOWED_HOSTS', '').split(',') if h.strip()
]
# Приватные файлы (фото трекинга): вне MEDIA_ROOT, nginx их напрямую не отдаёт.
PRIVATE_MEDIA_ROOT = os.environ.get('PRIVATE_MEDIA_ROOT', '') or os.path.join(BASE_DIR, 'private_media')
# true — отдавать через nginx (X-Accel-Redirect на internal-location /protected-media/).
# Срок жизни подписанной ссылки S3 на приватный файл, секунд.
PRIVATE_MEDIA_URL_EXPIRE = int(os.environ.get('PRIVATE_MEDIA_URL_EXPIRE', '300'))
PRIVATE_MEDIA_USE_X_ACCEL = os.environ.get('PRIVATE_MEDIA_USE_X_ACCEL', 'false').lower() in ('true', '1', 'yes')

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Раньше было CORS_ALLOW_ALL_ORIGINS = DEBUG. Из-за DEBUG=true в .env бэкенд
# в Docker отдавал Access-Control-Allow-Origin любому сайту вместе с
# Allow-Credentials: true — то есть чужая страница могла ходить в API от имени
# залогиненного пользователя. Отдельный флаг: включать только осознанно.
CORS_ALLOW_ALL_ORIGINS = os.environ.get('CORS_ALLOW_ALL_ORIGINS', 'false').lower() in ('true', '1', 'yes')
_cors_env = os.environ.get('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = (
    [o.strip() for o in _cors_env.split(',') if o.strip()]
    if _cors_env
    else ['http://localhost:3000', 'http://127.0.0.1:3000']
)
# С задачи 1.3 вход живёт в cookie: «все origin» + credentials позволили бы
# любому сайту читать личные данные пользователя. Открытый CORS — только без cookie.
CORS_ALLOW_CREDENTIALS = not CORS_ALLOW_ALL_ORIGINS

# ─── CSRF (задача 1.3) ────────────────────────────────────────────────────────
# JWT лежит в httpOnly-cookie, поэтому запросы, аутентифицированные cookie,
# проверяются на CSRF (users/authentication.py). Фронт читает csrftoken из
# cookie (GET /api/v1/auth/csrf/) и шлёт его в заголовке X-CSRFToken.
_csrf_env = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = (
    [o.strip() for o in _csrf_env.split(',') if o.strip()]
    if _csrf_env
    else ['http://localhost:3000', 'http://127.0.0.1:3000']
)
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False   # фронт должен прочитать токен и вернуть в заголовке

# ─── JWT в cookie (задача 1.3) ────────────────────────────────────────────────
# Единое место параметров — users/cookies.py.
AUTH_COOKIE_ACCESS_NAME = os.environ.get('AUTH_COOKIE_ACCESS_NAME', 'access')
AUTH_COOKIE_REFRESH_NAME = os.environ.get('AUTH_COOKIE_REFRESH_NAME', 'refresh')
# Метка «есть сессия» для фронта (не httpOnly, без токена; задача 1.4). Имя жёстко
# совпадает с frontend/lib/session-hint.ts.
AUTH_COOKIE_HINT_NAME = 'has_session'
AUTH_COOKIE_SECURE = os.environ.get(
    'AUTH_COOKIE_SECURE', 'false' if DEBUG else 'true',
).lower() in ('true', '1', 'yes')
AUTH_COOKIE_SAMESITE = os.environ.get('AUTH_COOKIE_SAMESITE', 'Lax')
if AUTH_COOKIE_SAMESITE not in ('Lax', 'Strict'):
    # None отключило бы защиту от CSRF на уровне браузера (и без Secure cookie отбрасываются).
    raise ImproperlyConfigured('AUTH_COOKIE_SAMESITE: допустимо только Lax или Strict.')
AUTH_COOKIE_DOMAIN = os.environ.get('AUTH_COOKIE_DOMAIN', '') or None  # пусто = host-only
# Refresh-cookie уходит только на эндпоинты auth (refresh и logout).
AUTH_COOKIE_REFRESH_PATH = '/api/v1/auth/'
# Переходный режим 1.3 (токены ещё и в теле ответа) выключен в задаче 1.4:
# фронт живёт только на cookie. Bearer-клиенты получают токены иначе
# (в тестах — RefreshToken.for_user).
AUTH_TOKENS_IN_BODY = False

# ─── Rate Limiting (throttling) ───────────────────────────────────────────────
# Дефолты env-overridable. Дорогие внешние API (Opendatabot, NHTSA) — 10/час.
_THROTTLE_ANON = os.environ.get('THROTTLE_ANON_RATE', '60/hour')
_THROTTLE_USER = os.environ.get('THROTTLE_USER_RATE', '300/hour')
_THROTTLE_EXPENSIVE = os.environ.get('THROTTLE_EXPENSIVE_RATE', '10/hour')

# ─── Защита входа от перебора (задача 1.5) ───────────────────────────────────
# Сколько прокси стоит перед Django: DRF берёт IP клиента из XFF с конца.
# 0 — dev без прокси (REMOTE_ADDR); 1 — nginx из docker-compose; 2 — ещё и Cloudflare/LB.
NUM_PROXIES_COUNT = int(os.environ.get('NUM_PROXIES', '0'))
LOGIN_MAX_FAILURES = int(os.environ.get('LOGIN_MAX_FAILURES', '5'))
LOGIN_FAILURE_WINDOW_MINUTES = int(os.environ.get('LOGIN_FAILURE_WINDOW_MINUTES', '15'))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get('LOGIN_LOCKOUT_MINUTES', '15'))

# ─── Флаги модулей (задача 2.8) ───────────────────────────────────────────────
# Заморожены до разморозки соответствующих задач (2.9, 2.10, 2.11, 3.3). Читать только через core.modules.module_enabled.
LOTS_ENABLED = os.environ.get('LOTS_ENABLED', 'false').strip().lower() in ('true', '1', 'yes')
B2B_ENABLED = os.environ.get('B2B_ENABLED', 'false').strip().lower() in ('true', '1', 'yes')
DEALERS_ENABLED = os.environ.get('DEALERS_ENABLED', 'false').strip().lower() in ('true', '1', 'yes')
SHIPMENTS_ENABLED = os.environ.get('SHIPMENTS_ENABLED', 'false').strip().lower() in ('true', '1', 'yes')
# Задача 3.2a: платные VIN-отчёты и реестры (carVertical, Opendatabot) заморожены; NHTSA-декодер флагом не закрыт.
VIN_REPORTS_ENABLED = os.environ.get('VIN_REPORTS_ENABLED', 'false').strip().lower() in ('true', '1', 'yes')
# Q7: legacy cars (/api/calculate/, /api/list/). Код cars/ не меняется, выключается подключение маршрутов.
LEGACY_CARS_API_ENABLED = os.environ.get('LEGACY_CARS_API_ENABLED', 'false').strip().lower() in ('true', '1', 'yes')

# ─── Подтверждение email и антибот (задача 1.6) ──────────────────────────────
_TRUE = ('true', '1', 'yes')
EMAIL_VERIFY_TTL_HOURS = int(os.environ.get('EMAIL_VERIFY_TTL_HOURS', '48'))
# Срок ссылки сброса пароля (секунды); его читает django default_token_generator (задача 1.7).
PASSWORD_RESET_TIMEOUT = int(os.environ.get('PASSWORD_RESET_TIMEOUT', '3600'))
# false - ограничения до подтверждения email выключены (IsEmailVerified пропускает всех).
EMAIL_VERIFICATION_REQUIRED = os.environ.get('EMAIL_VERIFICATION_REQUIRED', 'true').lower() in _TRUE
# turnstile | honeypot | off. off допустим только при DEBUG=True и в тестах (system check).
# Honeypot работает всегда (кроме off); Turnstile добавляется поверх, когда задан секрет.
CAPTCHA_PROVIDER = os.environ.get('CAPTCHA_PROVIDER', 'honeypot').strip().lower()
TURNSTILE_SITE_KEY = os.environ.get('TURNSTILE_SITE_KEY', '')
TURNSTILE_SECRET_KEY = os.environ.get('TURNSTILE_SECRET_KEY', '')
# Срок жизни одноразового form_token (honeypot), секунды.
CAPTCHA_FORM_TOKEN_MAX_AGE = int(os.environ.get('CAPTCHA_FORM_TOKEN_MAX_AGE', '3600'))
# Минимум секунд между выдачей формы и отправкой (honeypot-режим без Turnstile).
CAPTCHA_MIN_FILL_SECONDS = int(os.environ.get('CAPTCHA_MIN_FILL_SECONDS', '3'))
# Вход: капча после N неудач (Q2); CAPTCHA_ON_LOGIN=true - требовать всегда.
CAPTCHA_LOGIN_AFTER_FAILURES = int(os.environ.get('CAPTCHA_LOGIN_AFTER_FAILURES', '3'))
CAPTCHA_ON_LOGIN = os.environ.get('CAPTCHA_ON_LOGIN', 'false').lower() in _TRUE
IS_TESTING = _TESTING

# ─── DRF ──────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # Bearer-заголовок, затем httpOnly-cookie access (с CSRF-проверкой).
        'users.authentication.CookieJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': _THROTTLE_ANON,
        'user': _THROTTLE_USER,
        'expensive': _THROTTLE_EXPENSIVE,
        'messages': os.environ.get('THROTTLE_MESSAGES_RATE', '30/hour'),
        'contact': os.environ.get('THROTTLE_CONTACT_RATE', '20/hour'),
        # Загрузка фото (задача 1.10): каждый запрос — декодирование и пересохранение картинок.
        'uploads': os.environ.get('THROTTLE_UPLOADS_RATE', '30/hour'),
        'login': os.environ.get('THROTTLE_LOGIN_RATE', '10/min'),
        'lead': os.environ.get('THROTTLE_LEAD_RATE', '5/hour'),
        'lead_export': os.environ.get('THROTTLE_LEAD_EXPORT_RATE', '10/hour'),
        'register': os.environ.get('THROTTLE_REGISTER_RATE', '5/hour'),
        'refresh': os.environ.get('THROTTLE_REFRESH_RATE', '30/min'),
        'verify_resend': os.environ.get('THROTTLE_VERIFY_RESEND_RATE', '3/hour'),
        'password_reset': os.environ.get('THROTTLE_PASSWORD_RESET_RATE', '5/hour'),
        # Выгрузка «Мої дані» (1.8): тяжёлый запрос по всем таблицам пользователя.
        'data_export': os.environ.get('THROTTLE_DATA_EXPORT_RATE', '5/day'),
        # Отчёты об ошибках фронтенда (7.6), на IP: не даёт забить мониторинг мусором.
        'client_errors': os.environ.get('THROTTLE_CLIENT_ERRORS_RATE', '20/hour'),
        # Калькулятор (2.6, 02-S2): каждый расчёт пишет Calculation.
        'calculator': os.environ.get('THROTTLE_CALCULATOR_RATE', '30/hour'),
        # Клиентские счётчики (8.7): публичный эндпоинт без ПДн, на IP.
        'metrics_event': os.environ.get('THROTTLE_METRICS_EVENT_RATE', '60/min'),
    },
    'NUM_PROXIES': NUM_PROXIES_COUNT,
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# 01-S15: схема и Swagger/Redoc в проде только для admin-роли; API_DOCS_PUBLIC=true открывает всем.
API_DOCS_PUBLIC = os.environ.get('API_DOCS_PUBLIC', 'false').lower() in ('true', '1', 'yes')
SPECTACULAR_SETTINGS = {
    'SERVE_PERMISSIONS': (
        ['rest_framework.permissions.AllowAny'] if API_DOCS_PUBLIC else ['users.permissions.IsAdminRole']
    ),
    'ENUM_NAME_OVERRIDES': {
        'VehicleFuelTypeEnum': ['petrol', 'diesel', 'electric', 'hybrid'],
        'LocalListingFuelTypeEnum': ['petrol', 'diesel', 'electric', 'hybrid', 'gas'],
        'CustomsExciseFuelTypeEnum': ['petrol', 'diesel', 'electric', 'hybrid', 'phev'],
        'VehicleSourceAuctionEnum': ['copart', 'iaai', 'other'],
        'CarStatusEnum': ['IN_USA', 'IN_TRANSIT', 'IN_UKRAINE'],
        'ListingStatusEnum': ['in_transit', 'in_stock', 'sold'],
        'ListingChannelEnum': ['retail', 'wholesale'],
        # Dotted path: у TextChoices есть подписи, хеш списка значений с ними не совпал бы.
        'LeadStatusEnum': 'leads.models.LeadStatus',
        'LeadSourceEnum': 'leads.models.LeadSource',
        'SourceEnum': ['manual', 'apify'],
        'ListingCurrencyEnum': ['USD', 'UAH', 'EUR'],
        'ShipmentStatusEnum': [
            'at_us_warehouse', 'loading', 'in_ocean',
            'at_eu_port', 'on_truck_to_ua', 'cleared', 'delivered',
        ],
        'LocalListingStatusEnum': [
            'draft', 'active', 'pending', 'rejected', 'expired', 'sold', 'hidden',
        ],
        'DealStatusEnum': ['proposed', 'confirmed', 'cancelled'],
        'PromotionTariffTypeEnum': ['renew', 'bump', 'top'],
        'ReportStatusEnum': ['new', 'reviewed', 'dismissed'],
        'PaymentStatusEnum': ['pending', 'completed', 'failed', 'reversed'],
        'DealerApplicationStatusEnum': ['pending', 'approved', 'rejected'],
        'NotificationTypeEnum': [
            'new_message', 'listing_approved', 'listing_rejected', 'listing_expiring',
            'saved_search_match', 'deal_proposed', 'deal_confirmed', 'deal_cancelled',
            'review_received',
        ],
        'UserRoleEnum': ['buyer', 'dealer', 'broker', 'moderator', 'admin'],
    },
    'ENUM_GENERATE_CHOICE_DESCRIPTION': False,
    'TITLE': 'AUTOforYOU API',
    'DESCRIPTION': (
        'Маркетплейс для автоперекупщиков: импорт битых авто с аукционов США '
        '(Copart/IAAI), калькулятор стоимости «под ключ» в Украину, каталог объявлений.\n\n'
        '**Аутентификация**: `POST /api/v1/auth/token/` ставит httpOnly-cookie `access` и `refresh`. '
        'Для браузера: cookie `access` + заголовок `X-CSRFToken` на небезопасных методах '
        '(токен — из cookie `csrftoken`, её ставит `GET /api/v1/auth/csrf/`). '
        'Для API-клиентов: заголовок `Authorization: Bearer <access>`, CSRF не нужен.\n\n'
        '⚠ **Тестовые тарифы** — все расчёты демонстрационные до подключения реальных ставок.'
    ),
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'TAGS': [
        {'name': 'auth', 'description': 'Регистрация и JWT-аутентификация'},
        {'name': 'me', 'description': 'Личный кабинет (история расчётов, партнёры, контейнеры)'},
        {'name': 'vehicles', 'description': 'Каталог автомобилей + VIN-отчёты'},
        {'name': 'pricing', 'description': 'Калькулятор стоимости «под ключ» и тарифы'},
        {'name': 'listings', 'description': 'Объявления маркетплейса'},
        {'name': 'shipments', 'description': 'Логистика контейнеров'},
        {'name': 'b2b', 'description': 'B2B-доска опта (только верифицированные дилеры)'},
        {'name': 'payments', 'description': 'Платёжный шлюз LiqPay (checkout + webhook)'},
        {'name': 'lots', 'description': 'Импорт лотов аукционов (только admin)'},
        {'name': 'local', 'description': 'C2C: місцеві оголошення від користувачів (Каталог Україна)'},
        {'name': 'legacy', 'description': 'Устаревшие эндпоинты'},
    ],
}

# ─── Платёжный шлюз LiqPay ────────────────────────────────────────────────────
LIQPAY_PUBLIC_KEY = os.environ.get('LIQPAY_PUBLIC_KEY', '')
LIQPAY_PRIVATE_KEY = os.environ.get('LIQPAY_PRIVATE_KEY', '')
LIQPAY_SANDBOX = os.environ.get('LIQPAY_SANDBOX', 'true').lower() == 'true'

# ─── Аукционные сборы ─────────────────────────────────────────────────────────
AUCTION_DEFAULT_MEMBER_TYPE = os.environ.get('AUCTION_DEFAULT_MEMBER_TYPE', 'broker')
# Анонимные расчёты старше N дней удаляет pricing.tasks.purge_anonymous_calculations (2.6, 02-S2).
ANON_CALCULATION_TTL_DAYS = int(os.environ.get('ANON_CALCULATION_TTL_DAYS', '30'))

# ─── Anti-spam ────────────────────────────────────────────────────────────────
# 'soft' = flag listings for review, warn in message response (default)
# 'hard' = block listing creation, refuse to send message
# 'off'  = detection disabled
ANTISPAM_MODE = os.environ.get('ANTISPAM_MODE', 'soft')

# ─── Рейтинги продавця ────────────────────────────────────────────────────────
# Кількість підтверджених угод для отримання бейджа «Перевірений продавець»
SELLER_BADGE_THRESHOLD = int(os.environ.get('SELLER_BADGE_THRESHOLD', '3'))

# ─── C2C: місцеві оголошення ──────────────────────────────────────────────────
# Максимум активних оголошень на акаунт.
LOCAL_LISTING_MAX_ACTIVE = int(os.environ.get('LOCAL_LISTING_MAX_ACTIVE', '10'))
# Фото: максимальна кількість на оголошення і розмір файлу
LOCAL_LISTING_MAX_PHOTOS = int(os.environ.get('LOCAL_LISTING_MAX_PHOTOS', '15'))
# Пусто — общий UPLOAD_IMAGE_MAX_SIZE_MB (задача 1.10).
LOCAL_LISTING_PHOTO_MAX_SIZE_MB = int(os.environ.get('LOCAL_LISTING_PHOTO_MAX_SIZE_MB', '') or 0) or None
LOCAL_LISTING_EXPIRY_DAYS = int(os.environ.get('LOCAL_LISTING_EXPIRY_DAYS', '30'))

# ─── Внешние API ──────────────────────────────────────────────────────────────
# Opendatabot — реестры авто Украины. Без ключа → demo=True, не падает.
OPENDATABOT_API_KEY = os.environ.get('OPENDATABOT_API_KEY', '')

# Apify — скрейпер лотов аукционов. Без токена → demo=True, не падает.
APIFY_TOKEN = os.environ.get('APIFY_TOKEN', '')
CARVERTICAL_API_KEY = os.environ.get('CARVERTICAL_API_KEY', '')
# Партнёрская ссылка carVertical (выдаёт программа партнёров). Пусто - ссылка на сайте не показывается.
CARVERTICAL_PARTNER_URL = os.environ.get('CARVERTICAL_PARTNER_URL', '').strip()

# Режимы провайдеров (задача 3.1): auto | real | demo | off. auto: ключ задан и не плейсхолдер -> real,
# иначе off («не налаштовано»). Недопустимое значение -> ошибка manage.py check (integrations.E001).
NBU_MODE = os.environ.get('NBU_MODE', '').strip().lower() or 'auto'
VIN_DECODE_MODE = os.environ.get('VIN_DECODE_MODE', '').strip().lower() or 'auto'
# VIN-отчёт и Opendatabot заморожены (3.2a): по умолчанию off.
VIN_REPORT_MODE = os.environ.get('VIN_REPORT_MODE', '').strip().lower() or 'off'
OPENDATABOT_MODE = os.environ.get('OPENDATABOT_MODE', '').strip().lower() or 'off'
LOTS_MODE = os.environ.get('LOTS_MODE', '').strip().lower() or 'auto'
LIQPAY_MODE = os.environ.get('LIQPAY_MODE', '').strip().lower() or 'auto'
EMAIL_MODE = os.environ.get('EMAIL_MODE', '').strip().lower() or 'auto'
TELEGRAM_MODE = os.environ.get('TELEGRAM_MODE', '').strip().lower() or 'auto'
# Общий таймаут HTTP-вызовов провайдеров, секунды (03-C9).
try:
    INTEGRATIONS_HTTP_TIMEOUT = int(os.environ.get('INTEGRATIONS_HTTP_TIMEOUT', '') or 10)
except ValueError:
    INTEGRATIONS_HTTP_TIMEOUT = 10
if INTEGRATIONS_HTTP_TIMEOUT <= 0:
    INTEGRATIONS_HTTP_TIMEOUT = 10

# ─── Email ────────────────────────────────────────────────────────────────────
# Dev: console-вывод. Продакшен: вписати SMTP-провайдер через env EMAIL_BACKEND=...smtp...
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '25'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'false').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', '') or 'noreply@localhost'

# ─── JWT ──────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.environ.get('JWT_ACCESS_MINUTES', '15'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.environ.get('JWT_REFRESH_DAYS', '7'))),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,   # отзывает старый refresh при ротации
    'AUTH_HEADER_TYPES': ('Bearer',),
    'UPDATE_LAST_LOGIN': True,          # админка показывает реальный last_login (01-Q7)
}

# ─── Celery ───────────────────────────────────────────────────────────────────
# Нет REDIS_URL или CELERY_EAGER=true → задачи выполняются синхронно (eager).
# 01-C13: eager включается отдельным флагом, а не от DEBUG.
CELERY_EAGER = os.environ.get('CELERY_EAGER', 'false').lower() in ('true', '1', 'yes')
if _REDIS_URL and not CELERY_EAGER:
    CELERY_BROKER_URL = _REDIS_URL
    CELERY_RESULT_BACKEND = _REDIS_URL
    CELERY_TASK_ALWAYS_EAGER = False
else:
    CELERY_BROKER_URL = 'memory://'
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# Celery не перехватывает корневой логгер: иначе логи задач шли бы мимо фильтра ПДн из LOGGING (7.2).
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
# Повторы задач с базой core.tasks.ResilientTask и журнал упавших задач (8.9).
# Без префикса CELERY_: Celery читает settings с namespace='CELERY', и CELERY_TASK_ACKS_LATE стал бы
# глобальным task_acks_late для всех задач (дубли Telegram и писем при падении воркера).
RESILIENT_TASK_MAX_RETRIES = int(os.environ.get('RESILIENT_TASK_MAX_RETRIES', '3'))
# true: сообщение подтверждается после выполнения - при падении воркера задача не теряется (возможен повтор).
RESILIENT_TASK_ACKS_LATE = os.environ.get('RESILIENT_TASK_ACKS_LATE', 'true').lower() in ('true', '1', 'yes')
FAILED_TASK_RETENTION_DAYS = int(os.environ.get('FAILED_TASK_RETENTION_DAYS', '90'))
# Строки аргументов длиннее (или с пробелами - тексты) пишутся только как <str:длина>.
FAILED_TASK_ARG_MAX_LEN = int(os.environ.get('FAILED_TASK_ARG_MAX_LEN', '64'))
CELERY_TIMEZONE = 'Europe/Kyiv'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Расписание фоновых задач
from celery.schedules import crontab as _crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Очистка старых анонимных расчётов (2.6, 02-S2)
    'purge-anonymous-calculations-daily': {
        'task': 'pricing.tasks.purge_anonymous_calculations',
        'schedule': _crontab(hour=3, minute=45),
    },
    # Курс НБУ: каждый день в 09:00 по Киеву
    'fetch-nbu-rates-daily': {
        'task': 'pricing.tasks.fetch_nbu_rates_task',
        'schedule': _crontab(hour=9, minute=0),
    },
    # Saved searches: щодня о 10:00 — перевірка нових оголошень і надсилання алертів
    'check-saved-searches-daily': {
        'task': 'saved_searches.tasks.check_saved_searches',
        'schedule': _crontab(hour=10, minute=0),
    },
    # Попередження про закінчення оголошення (за 3 дні), один раз
    'warn-expiring-listings-daily': {
        'task': 'local_listings.tasks.warn_expiring_listings',
        'schedule': _crontab(hour=9, minute=15),
    },
    # Авто-зняття прострочених оголошень
    'expire-listings-daily': {
        'task': 'local_listings.tasks.expire_listings',
        'schedule': _crontab(hour=9, minute=20),
    },
    # Чистка просроченных JWT в blacklist и сессий Django (01-Q1)
    'flush-expired-tokens-daily': {
        'task': 'users.tasks.flush_expired_tokens',
        'schedule': _crontab(hour=3, minute=30),
    },
    # Обезличивание аккаунтов после периода отмены (1.8, Q3)
    'anonymize-due-accounts-daily': {
        'task': 'users.tasks.anonymize_due_accounts',
        'schedule': _crontab(hour=3, minute=45),
    },
    # Чистка журнала упавших задач старше FAILED_TASK_RETENTION_DAYS (8.9)
    'purge-failed-tasks-daily': {
        'task': 'task_ledger.tasks.purge_failed_tasks',
        'schedule': _crontab(hour=4, minute=10),
    },
    # Досыл журнала заявок в группу с партнёром (2.15), порог возраста - в админке
    'resend-lead-journal': {
        'task': 'leads.tasks.resend_journal',
        'schedule': _crontab(minute='*/5'),
    },
}

# ─── Telegram-бот ─────────────────────────────────────────────────────────────
# Без TELEGRAM_BOT_TOKEN бот не стартует; run_bot завершается с понятным сообщением.
# Сайт и все API работают как обычно — токен нужен только боту.
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

# В тестах токен всегда пустой.
# post_save на listings.Listing запускает post_listing_to_channel, а в тестах
# CELERY_TASK_ALWAYS_EAGER=True — задача выполняется синхронно и с реальным
# токеном уходит в api.telegram.org. Прогон listings занимал 22.5 с вместо
# 4.5 с, и это были настоящие аутентифицированные запросы боевым ботом.
# (обнуление — в блоке изоляции тестов в конце файла)
TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME', '')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '')      # @channel или -100xxx
TELEGRAM_B2B_CHANNEL_ID = os.environ.get('TELEGRAM_B2B_CHANNEL_ID', '')  # опц. B2B-канал
TELEGRAM_WEBHOOK_SECRET = os.environ.get('TELEGRAM_WEBHOOK_SECRET', '')   # для прод. webhook
# Запасной chat_id брокера/группы брокеров (основной задаётся в админке, задача 2.2)
TELEGRAM_BROKER_CHAT_ID = os.environ.get('TELEGRAM_BROKER_CHAT_ID', '')
# Журнал заявок в группу с партнёром (2.15): только AFY-ID, авто, бюджет, город, время; без ПДн.
LEAD_JOURNAL_CHAT_ID = os.environ.get('LEAD_JOURNAL_CHAT_ID', '')

# URL сайта — используется в Telegram-постах (ссылки на листинги)
SITE_URL = os.environ.get('SITE_URL', '') or 'http://localhost'

# ─── Заголовки безопасности (только в продакшене) ─────────────────────────────
# В dev (DEBUG=True) и в тест-раннере не включаем — тесты работают по HTTP.
if not DEBUG and not _TESTING:
    # Отключается только осознанно: стенд без TLS (CI, локальный прогон
    # E2E по HTTP) или TLS, терминируемый балансировщиком, который уже
    # делает редирект сам. По умолчанию включено.
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'true').lower() in ('true', '1', 'yes')
    SECURE_HSTS_SECONDS = 31_536_000 if SECURE_SSL_REDIRECT else 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    # csrftoken живёт в паре с auth-cookie (задача 1.4): один флаг на оба. Выключать
    # только на стенде без TLS (локальный e2e по HTTP), по умолчанию на проде true.
    CSRF_COOKIE_SECURE = AUTH_COOKIE_SECURE
    if SECURE_SSL_REDIRECT and not AUTH_COOKIE_SECURE:
        # Флаг стенда без TLS (.env.e2e) не должен попасть на прод с HTTPS.
        raise ImproperlyConfigured('AUTH_COOKIE_SECURE=false допустим только при SECURE_SSL_REDIRECT=false.')
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    X_FRAME_OPTIONS = 'DENY'
    SECURE_CONTENT_TYPE_NOSNIFF = True


# ─── Изоляция тестов от внешнего мира (задача 0.2) ────────────────────────────
# Результат тестов не должен зависеть от локального .env.
# ПРАВИЛО: любой новый ключ внешнего провайдера (carVertical и др. этапа 3,
# Turnstile и т.п.) добавлять сюда. Тесты, которым нужен ключ, задают его
# через override_settings, а не берут из окружения.
TEST_RUNNER = 'core.test_runner.IsolatedDiscoverRunner'

if _TESTING:
    # Модули включены, отдельные тесты выключают их через override_settings (задача 2.8).
    LOTS_ENABLED = True
    B2B_ENABLED = True
    DEALERS_ENABLED = True
    SHIPMENTS_ENABLED = True
    VIN_REPORTS_ENABLED = True
    CARVERTICAL_PARTNER_URL = ''
    LEGACY_CARS_API_ENABLED = False
    OPENDATABOT_API_KEY = ''
    APIFY_TOKEN = ''
    CARVERTICAL_API_KEY = ''
    NBU_MODE = VIN_DECODE_MODE = VIN_REPORT_MODE = OPENDATABOT_MODE = 'auto'
    LOTS_MODE = LIQPAY_MODE = EMAIL_MODE = TELEGRAM_MODE = 'auto'
    INTEGRATIONS_HTTP_TIMEOUT = 10
    LIQPAY_PUBLIC_KEY = ''
    LIQPAY_PRIVATE_KEY = ''
    TELEGRAM_BOT_TOKEN = ''
    TELEGRAM_BROKER_CHAT_ID = ''
    LEAD_JOURNAL_CHAT_ID = ''
    LOT_PHOTO_ALLOWED_HOSTS = []
    PRIVATE_MEDIA_USE_X_ACCEL = False
    TURNSTILE_SITE_KEY = ''
    TURNSTILE_SECRET_KEY = ''
    CAPTCHA_PROVIDER = 'off'
    CAPTCHA_ON_LOGIN = False
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    EMAIL_HOST_USER = ''
    EMAIL_HOST_PASSWORD = ''
    # Кэш и Celery не должны подключаться к Redis, даже если задан REDIS_URL.
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'cache+memory://'
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# ─── Логи (задача 7.2, 12-S8, 01-S14) ─────────────────────────────────────────
# stdout, на всех handler'ах фильтр ПДн (core/logging_filters.py). django.request - путь без query.
# httpx/httpcore на WARNING: на INFO они пишут полные URL запросов (в т.ч. с apikey=).
# В тестах по умолчанию WARNING: INFO-логи сервисов засоряли бы вывод прогона (assertLogs ставит уровень сам).
LOG_LEVEL = os.environ.get('LOG_LEVEL', '').upper() or ('WARNING' if _TESTING else 'INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'pii': {'()': 'core.logging_filters.PiiScrubFilter'},
        'request_path': {'()': 'core.logging_filters.RequestPathFilter'},
    },
    'formatters': {
        'default': {'format': '%(asctime)s %(levelname)s %(name)s: %(message)s'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'formatter': 'default',
            'filters': ['request_path', 'pii'],
        },
    },
    'root': {'handlers': ['console'], 'level': LOG_LEVEL},
    'loggers': {
        'django': {'handlers': ['console'], 'level': LOG_LEVEL, 'propagate': False},
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        'httpx': {'level': 'WARNING'},
        'httpcore': {'level': 'WARNING'},
    },
}

# Приватные файлы (фото трекинга) при публичном CDN-домене: отдельный bucket без публичного домена.
PRIVATE_S3_BUCKET_NAME = os.environ.get('PRIVATE_S3_BUCKET_NAME', '')
if globals().get('USE_S3') and globals().get('AWS_S3_CUSTOM_DOMAIN'):
    if not PRIVATE_S3_BUCKET_NAME and not _TESTING:
        import logging as _logging
        _logging.getLogger('core.settings').warning(
            'S3_CUSTOM_DOMAIN раздаёт весь bucket публично, а приватные фото трекинга лежат в нём же '
            '(private/). Задайте PRIVATE_S3_BUCKET_NAME (bucket без публичного домена) или закройте '
            '/private/* правилом CDN.')

if not DEBUG and not _TESTING and SITE_URL.startswith(('http://localhost', 'http://127.0.0.1')):
    import logging as _logging
    _logging.getLogger('core.settings').warning(
        'SITE_URL указывает на localhost при DEBUG=false: ссылки в письмах будут вести на localhost. '
        'Задайте SITE_URL=https://домен в .env.')
