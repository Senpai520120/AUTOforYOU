import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-ea+&)bt%jlzm6=lms#20m8khy&^!fg*41^a+l(&3n7e!5hoal+'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    'users',
    'vehicles',
    'pricing',
    'listings',
    'shipments',
    'integrations',
    'payments',
    'cars',

    'drf_spectacular',
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

STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]
CORS_ALLOW_CREDENTIALS = True

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
        {'name': 'legacy', 'description': 'Устаревшие эндпоинты'},
    ],
}

# LiqPay — ключи из env. Для sandbox: LIQPAY_SANDBOX=true
LIQPAY_PUBLIC_KEY = os.environ.get('LIQPAY_PUBLIC_KEY', '')
LIQPAY_PRIVATE_KEY = os.environ.get('LIQPAY_PRIVATE_KEY', '')
LIQPAY_SANDBOX = os.environ.get('LIQPAY_SANDBOX', 'true').lower() == 'true'

# Аукционные сборы — тип участника по умолчанию (public / licensed / broker)
AUCTION_DEFAULT_MEMBER_TYPE = os.environ.get('AUCTION_DEFAULT_MEMBER_TYPE', 'broker')

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}
