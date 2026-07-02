import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root (next to manage.py).
# encoding='utf-8' is explicit — avoids any system-locale surprises on Windows.
load_dotenv(BASE_DIR / '.env', encoding='utf-8', override=False)

# ─── Безопасность ─────────────────────────────────────────────────────────────
# В продакшене задать через env: SECRET_KEY=<случайная_строка>
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-ea+&)bt%jlzm6=lms#20m8khy&^!fg*41^a+l(&3n7e!5hoal+',
)

# DEBUG=False по умолчанию; для локальной разработки добавить DEBUG=true в .env
DEBUG = os.environ.get('DEBUG', 'false').lower() in ('true', '1', 'yes')

# In production set: ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
_raw_hosts = os.environ.get('ALLOWED_HOSTS', '')
_testing = 'test' in sys.argv
_explicit_hosts = [h.strip() for h in _raw_hosts.split(',') if h.strip()]
if _explicit_hosts:
    ALLOWED_HOSTS = _explicit_hosts
elif DEBUG:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']
elif _testing:
    ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
else:
    ALLOWED_HOSTS = []   # prod without env var → Django will raise, as intended

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

    'drf_spectacular',
    'django_celery_beat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
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

# ─── Медиафайлы и хранилище ───────────────────────────────────────────────────
# Не заданы S3_*-переменные → локальное хранилище /media/ (dev рабочий без S3).
# Заданы все три (S3_BUCKET_NAME, S3_REGION, AWS_ACCESS_KEY_ID + SECRET_ACCESS_KEY)
# → медиафайлы идут в AWS S3 (или совместимое хранилище).

_S3_BUCKET = os.environ.get('S3_BUCKET_NAME', '')
_S3_REGION = os.environ.get('S3_REGION', 'eu-central-1')
_AWS_KEY = os.environ.get('AWS_ACCESS_KEY_ID', '')
_AWS_SECRET = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
_S3_ENDPOINT = os.environ.get('S3_ENDPOINT_URL', '')  # для S3-совместимых (Cloudflare R2, MinIO)

USE_S3 = bool(_S3_BUCKET and _AWS_KEY and _AWS_SECRET)

if USE_S3:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'

    AWS_ACCESS_KEY_ID = _AWS_KEY
    AWS_SECRET_ACCESS_KEY = _AWS_SECRET
    AWS_STORAGE_BUCKET_NAME = _S3_BUCKET
    AWS_S3_REGION_NAME = _S3_REGION
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = 'private'
    AWS_QUERYSTRING_AUTH = True          # подписанные URL (приватный bucket)
    AWS_S3_SIGNATURE_VERSION = 's3v4'

    if _S3_ENDPOINT:
        AWS_S3_ENDPOINT_URL = _S3_ENDPOINT  # Cloudflare R2 / MinIO

    MEDIA_URL = f'https://{_S3_BUCKET}.s3.{_S3_REGION}.amazonaws.com/'
    STATIC_URL = MEDIA_URL + 'static/'
else:
    MEDIA_URL = '/media/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
    STATIC_URL = 'static/'

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Dev: разрешаем всё. Prod: задать CORS_ALLOWED_ORIGINS=https://yourdomain.com,...
CORS_ALLOW_ALL_ORIGINS = DEBUG
_cors_env = os.environ.get('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = (
    [o.strip() for o in _cors_env.split(',') if o.strip()]
    if _cors_env
    else ['http://localhost:3000', 'http://127.0.0.1:3000']
)
CORS_ALLOW_CREDENTIALS = True

# ─── Rate Limiting (throttling) ───────────────────────────────────────────────
# Дефолты env-overridable. Дорогие внешние API (Opendatabot, NHTSA) — 10/час.
_THROTTLE_ANON = os.environ.get('THROTTLE_ANON_RATE', '60/hour')
_THROTTLE_USER = os.environ.get('THROTTLE_USER_RATE', '300/hour')
_THROTTLE_EXPENSIVE = os.environ.get('THROTTLE_EXPENSIVE_RATE', '10/hour')

# ─── DRF ──────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
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
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'ENUM_NAME_OVERRIDES': {
        'VehicleFuelTypeEnum': ['petrol', 'diesel', 'electric', 'hybrid'],
        'VehicleSourceAuctionEnum': ['copart', 'iaai', 'other'],
        'CarStatusEnum': ['IN_USA', 'IN_TRANSIT', 'IN_UKRAINE'],
        'ListingStatusEnum': ['in_transit', 'in_stock', 'sold'],
        'ListingChannelEnum': ['retail', 'wholesale'],
        'ListingCurrencyEnum': ['USD', 'UAH', 'EUR'],
        'ShipmentStatusEnum': [
            'at_us_warehouse', 'loading', 'in_ocean',
            'at_eu_port', 'on_truck_to_ua', 'cleared', 'delivered',
        ],
    },
    'TITLE': 'AUTOforYOU API',
    'DESCRIPTION': (
        'Маркетплейс для автоперекупщиков: импорт битых авто с аукционов США '
        '(Copart/IAAI), калькулятор стоимости «под ключ» в Украину, каталог объявлений.\n\n'
        '**Аутентификация**: Bearer JWT. Получить токен: `POST /api/v1/auth/token/`.\n\n'
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

# ─── C2C: місцеві оголошення ──────────────────────────────────────────────────
# Максимум активних оголошень на акаунт. Повний антиспам — C2C-промт 6.
LOCAL_LISTING_MAX_ACTIVE = int(os.environ.get('LOCAL_LISTING_MAX_ACTIVE', '10'))
# Фото: максимальна кількість на оголошення і розмір файлу
LOCAL_LISTING_MAX_PHOTOS = int(os.environ.get('LOCAL_LISTING_MAX_PHOTOS', '15'))
LOCAL_LISTING_PHOTO_MAX_SIZE_MB = int(os.environ.get('LOCAL_LISTING_PHOTO_MAX_SIZE_MB', '8'))
LOCAL_LISTING_EXPIRY_DAYS = int(os.environ.get('LOCAL_LISTING_EXPIRY_DAYS', '30'))

# ─── Внешние API ──────────────────────────────────────────────────────────────
# Opendatabot — реестры авто Украины. Без ключа → demo=True, не падает.
OPENDATABOT_API_KEY = os.environ.get('OPENDATABOT_API_KEY', '')

# Apify — скрейпер лотов аукционов. Без токена → demo=True, не падает.
APIFY_TOKEN = os.environ.get('APIFY_TOKEN', '')

# ─── Email ────────────────────────────────────────────────────────────────────
# Dev: console-вывод. Продакшен: EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@autoforyou.ua')

# ─── JWT ──────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,   # отзывает старый refresh при ротации
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ─── Celery ───────────────────────────────────────────────────────────────────
# Нет REDIS_URL ИЛИ DEBUG=True → задачи выполняются синхронно (eager).
# Тесты и локальная разработка работают без Redis-воркера.
if _REDIS_URL and not DEBUG:
    CELERY_BROKER_URL = _REDIS_URL
    CELERY_RESULT_BACKEND = _REDIS_URL
    CELERY_TASK_ALWAYS_EAGER = False
else:
    CELERY_BROKER_URL = 'memory://'
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

CELERY_TIMEZONE = 'Europe/Kyiv'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Расписание фоновых задач
from celery.schedules import crontab as _crontab  # noqa: E402
CELERY_BEAT_SCHEDULE = {
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
}

# ─── Telegram-бот ─────────────────────────────────────────────────────────────
# Без TELEGRAM_BOT_TOKEN бот не стартует; run_bot завершается с понятным сообщением.
# Сайт и все API работают как обычно — токен нужен только боту.
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME', '')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '')      # @channel или -100xxx
TELEGRAM_B2B_CHANNEL_ID = os.environ.get('TELEGRAM_B2B_CHANNEL_ID', '')  # опц. B2B-канал
TELEGRAM_WEBHOOK_SECRET = os.environ.get('TELEGRAM_WEBHOOK_SECRET', '')   # для прод. webhook

# URL сайта — используется в Telegram-постах (ссылки на листинги)
SITE_URL = os.environ.get('SITE_URL', 'https://autoforyou.ua')

# ─── Заголовки безопасности (только в продакшене) ─────────────────────────────
# В dev (DEBUG=True) и в тест-раннере не включаем — тесты работают по HTTP.
_TESTING = 'test' in sys.argv
if not DEBUG and not _TESTING:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31_536_000          # 1 год
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    X_FRAME_OPTIONS = 'DENY'
    SECURE_CONTENT_TYPE_NOSNIFF = True
