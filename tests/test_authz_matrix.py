"""Общая матрица прав 401/403/404 по всем эндпоинтам API (задача 1.11, бриф §3).

Одна строка `Case` = один (url_name, метод). Для каждой строки генерируются отдельные
тест-методы (откат БД между ними, фикстуры строятся один раз в setUpTestData):

- anon: аноним -> 401, данные не изменены;
- other: посторонний пользователь -> код из строки (403/404; для «своих» эндпоинтов - 200
  над СВОИМИ данными), данные владельца не изменены, чужих id/маркеров в ответе нет;
- owner: владелец -> код из строки (и его id есть в списке);
- role_<роль>: staff/broker/moderator/admin/dealer/unverified - код из `roles` строки;
- csrf: тот же владелец с cookie-сессией и БЕЗ X-CSRFToken -> 403, данные не изменены.

Тест полноты обходит `get_resolver()`: приватный view без строки в матрице (и не в белом списке
публичных) роняет тест с именем URL. Строки «ждёт задачу N» помечены в `note`.
Фабрики - tests/factories.py. Правила и таблица «требование §3 -> тест» - docs/BACKEND_TESTS.md.
"""
import shutil
import tempfile
import unittest
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import NoReverseMatch, URLPattern, URLResolver, get_resolver, path, reverse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from deals.models import Deal, Review
from deals.services import confirm_deal, propose_deal
from favorites.models import Favorite
from leads.models import Lead
from leads.services import create_lead
from local_listings.models import LocalListing, LocalListingImage
from messaging.models import Conversation, Message
from messaging.services import get_or_create_conversation
from notifications.models import Notification
from payments.models import Payment
from pricing.models import Calculation
from saved_searches.models import SavedSearch
from shipments.models import Shipment
from site_settings.models import SiteSettings
from tests.base import CleanCacheTestCase
from tests.factories import (
    TEST_PASSWORD,
    auth_client,
    make_admin_role,
    make_broker,
    make_dealer,
    make_local_listing,
    make_moderator,
    make_staff,
    make_user,
)
from tests.test_uploads import image_bytes
from users.models import CustomUser, DealerApplication, TrustedShop

API = 'api/v1/'

# --------------------------------------------------------------------------------------
# Белый список публичных эндпоинтов (23-D34). Новая запись - только с обоснованием.
# --------------------------------------------------------------------------------------
PUBLIC = {
    # вход/регистрация/сброс пароля: гость по определению (защита - капча, лимиты, lockout)
    'auth-register': 'регистрация',
    'auth-verify-email': 'ссылка из письма, токен в теле',
    'auth-config': 'публичная конфигурация без секретов',
    'auth-csrf': 'выдача CSRF-cookie',
    'token-obtain': 'вход',
    'token-refresh': 'refresh из cookie/тела (CSRF для cookie)',
    'token-logout': 'выход идемпотентен, чужой refresh не отзывается (01-S13)',
    'auth-password-reset': 'запрос сброса, всегда одинаковый ответ',
    'auth-password-reset-confirm': 'токен из письма',
    # публичный каталог и расчёт
    'vehicle-list': 'каталог',
    'vehicle-detail': 'каталог',
    'vin-decode': 'публичная расшифровка VIN',
    'pricing-calculate': 'калькулятор',
    'pricing-rates': 'ставки: ждёт задачу 2.6 - по Q8 суммы должны видеть только staff/broker (см. PricingRatesAwaiting26)',
    'listing-list': 'каталог',
    'listing-detail': 'каталог',
    'local-tariffs': 'тарифы',
    'local-vin-prefill': 'подсказка по VIN',
    'local-regions': 'справочник',
    'local-cities': 'справочник',
    'seller-rating': 'публичный рейтинг, 404 без активных объявлений (06-S12)',
    'site-settings': 'публичные настройки сайта',
    'content-how-it-works': 'публичные тексты «Як працює пригон» (2.13): только активные записи, без служебных полей',
    'content-faq': 'публичный FAQ (2.13): только активные записи, без служебных полей',
    'landing-list': 'публичный список страниц моделей (2.16): slug, марка, модель, итог; без ПДн и записи в БД',
    'landing-detail': 'публичная страница модели с расчётом (2.16): только опубликованные, 404 иначе, без записи в БД',
    'lead-create': 'заявка от гостя: капча, honeypot, лимит (2.1a)',
    'monitoring-client-errors': 'отчёт об ошибке фронтенда: без сессии, только запись в мониторинг, лимит на IP (7.6)',
    'metrics-event': 'дневной счётчик без ПДн: whitelist двух ключей, без сессии, лимит (8.7)',
    # не session/JWT, а подпись/секрет
    'liqpay-callback': 'подпись LiqPay (SHA1), csrf_exempt',
    'telegram-webhook': 'секрет X-Telegram-Bot-Api-Secret-Token (plain View)',
    # legacy 'calculator' и 'car-list' подключаются только при LEGACY_CARS_API_ENABLED (2.8, по умолчанию выключен)
}
# Публичные методы у смешанных view (остальные методы обязаны быть в матрице).
PUBLIC_METHODS = {
    'local-listing-list': {'get'},
    'local-listing-detail': {'get'},
}
HANDLER_METHODS = ('get', 'post', 'put', 'patch', 'delete')


@dataclass
class Case:
    name: str                                   # url_name
    method: str                                 # get/post/put/patch/delete
    kwargs: Callable[[Any], dict] = lambda c: {}    # noqa: E731 - kwargs для reverse
    payload: Callable[[Any], Any] | dict | None = None
    fmt: str = 'json'
    query: str = ''
    owner: str = 'a'                            # кто «владелец» (ключ ctx.u)
    owner_code: int = 200
    other: int = 404                            # код для постороннего (ctx.u['b'])
    roles: dict = field(default_factory=dict)   # роль -> код
    state: Callable[[Any], Any] | None = None   # снимок данных владельца (не должен меняться)
    ids: Callable[[Any], set] | None = None     # id объектов владельца в списке
    forbid: Callable[[Any], list] | None = None  # маркеры владельца, которых нет в ответе постороннему
    variant: str = ''
    csrf: bool = True
    note: str = ''

    @property
    def cid(self):
        base = f'{self.name}__{self.method}' + (f'__{self.variant}' if self.variant else '')
        return base.replace('-', '_')


# ----------------------------- снимки состояния --------------------------------------
def _vals(qs, *fields):
    return list(qs.order_by('pk').values_list('pk', *fields))


def st_user(c):
    return list(CustomUser.objects.filter(pk=c.u['a'].pk).values_list(
        'password', 'session_version', 'first_name', 'last_name', 'phone', 'telegram_id', 'role',
        'deletion_scheduled_at', 'deleted_at', 'email'))


def st_shops(c):
    return _vals(TrustedShop.objects.filter(owner=c.u['a']), 'name', 'type', 'contacts', 'rating', 'notes')


def st_apps(c):
    return _vals(DealerApplication.objects.filter(user=c.u['a']), 'status', 'company_name')


def st_deals(c):
    return (
        _vals(Deal.objects.all(), 'status'),
        _vals(Review.objects.all(), 'rating'),
        _vals(LocalListing.objects.filter(owner=c.u['a']), 'status'),
    )


def st_msgs(c):
    return _vals(Message.objects.filter(conversation_id=c.conv), 'text', 'read_at')


def st_notifs(c):
    return _vals(Notification.objects.filter(user=c.u['a']), 'is_read')


def st_favs(c):
    return _vals(Favorite.objects.filter(user=c.u['a']))


def st_searches(c):
    return _vals(SavedSearch.objects.filter(user=c.u['a']), 'name', 'filters', 'notify')


def st_listings(c):
    return _vals(LocalListing.objects.filter(owner=c.u['a']), 'status', 'price', 'description')


def st_images(c):
    return _vals(LocalListingImage.objects.filter(listing__owner=c.u['a']), 'listing_id', 'is_primary')


def st_leads(c):
    return _vals(Lead.objects.all(), 'status', 'assigned_to_id', 'partner_status')


def st_payments(c):
    return _vals(Payment.objects.filter(user=c.u['a']), 'status', 'amount')


def _lead_ids(c):
    return {c.lead}


def _ids(*attrs):
    return lambda c: {getattr(c, a) for a in attrs}


LISTING_PAYLOAD = lambda c: {  # noqa: E731
    'make': 'Toyota', 'model': 'Camry', 'year': 2020, 'mileage_km': 50000, 'engine_cc': 2500,
    'fuel_type': 'petrol', 'transmission': 'auto', 'body_type': 'sedan', 'condition': 'used',
    'price': '500000', 'currency': 'UAH', 'price_type': 'fixed', 'region': c.region,
    'city': c.city, 'description': 'Тест', 'contact_phone': '+380501234567', 'agreed_to_rules': True,
}

BROKER_ROLES = {'moderator': 403, 'staff': 403, 'dealer': 403, 'admin': 200}
LEAD_URL = lambda c: {'pk': c.lead}  # noqa: E731

MATRIX: list[Case] = [
    # ---- аккаунт (1.3, 1.6, 1.7, 1.8) ------------------------------------------------
    Case('auth-verify-email-resend', 'post', other=200, state=st_user,
         note='повторное письмо - только себе'),
    Case('token-logout-all', 'post', other=200, state=st_user,
         note='«выйти везде» отзывает только сессии вызвавшего (session_version чужого не меняется)'),
    Case('auth-password-change', 'post', other=200, state=st_user,
         payload={'old_password': TEST_PASSWORD, 'new_password': 'N3w-Str0ng-Pass-77',
                  'new_password2': 'N3w-Str0ng-Pass-77'},
         note='пароль меняется только у вызвавшего'),
    Case('auth-profile', 'get', other=200, forbid=lambda c: [c.u['a'].email]),
    Case('auth-profile', 'patch', other=200, state=st_user, payload={'first_name': 'Змінено'}),
    Case('auth-profile', 'put', other=200, state=st_user,
         payload={'first_name': 'Змінено', 'last_name': 'Тест', 'phone': '+380501112233'}),
    Case('auth-profile', 'delete', owner_code=202, other=202, state=st_user, payload={'password': TEST_PASSWORD},
         note='удаление ставится только своему аккаунту (пароль - свой)'),
    Case('auth-profile-cancel-deletion', 'post', other=200, state=st_user,
         note='отмена - только своего удаления'),
    Case('me-export', 'get', other=200, forbid=lambda c: [c.u['a'].email, 'СТО Секрет', 'Іван'],
         note='выгрузка только своих данных'),

    # ---- OpenAPI и документация (7.2, 01-S15): только admin-роль, API_DOCS_PUBLIC=true открывает всем
    Case('schema', 'get', owner='admin', other=403, roles={'staff': 403, 'broker': 403, 'admin': 200}),
    Case('swagger-ui', 'get', owner='admin', other=403, roles={'staff': 403, 'admin': 200}),
    Case('redoc', 'get', owner='admin', other=403, roles={'staff': 403, 'admin': 200}),

    # ---- личный кабинет (23-D6...D9) -------------------------------------------------
    Case('me-calculations', 'get', other=200, ids=_ids('calc')),
    Case('me-shipments', 'get', other=200, ids=_ids('shipment')),
    Case('me-trusted-shops', 'get', other=200, ids=_ids('shop')),
    Case('me-trusted-shops', 'post', owner_code=201, other=201, state=st_shops, payload={'name': 'Нове СТО'}),
    Case('me-trusted-shop-detail', 'get', kwargs=lambda c: {'pk': c.shop}, state=st_shops),
    Case('me-trusted-shop-detail', 'patch', kwargs=lambda c: {'pk': c.shop}, state=st_shops,
         payload={'name': 'Чужое'}),
    Case('me-trusted-shop-detail', 'put', kwargs=lambda c: {'pk': c.shop}, state=st_shops,
         payload={'name': 'Чужое', 'type': 'service', 'rating': 1}),
    Case('me-trusted-shop-detail', 'delete', kwargs=lambda c: {'pk': c.shop}, owner_code=204, state=st_shops),
    Case('dealer-apply', 'post', owner='e', owner_code=201, other=201, state=st_apps,
         roles={'unverified': 403},
         payload={'company_name': 'ТОВ Тест', 'full_name': 'Іван Петренко', 'contact_phone': '+380501112233',
                  'agreed_to_processing': True, 'confirmed_age_18': True}),
    Case('dealer-application', 'get', other=404, forbid=lambda c: ['Секретна Компанія']),

    # ---- сделки (23-D10, 13-S1) ------------------------------------------------------
    Case('deal-list-create', 'get', other=200, ids=_ids('deal_proposed', 'deal_confirmed')),
    Case('deal-list-create', 'post', owner_code=201, other=400, state=st_deals,
         payload=lambda c: {'listing_id': c.listing_deal, 'buyer_id': c.u['c'].pk},
         note='ValueError сервиса («тільки власник»), данные не меняются'),
    Case('deal-confirm', 'post', kwargs=lambda c: {'pk': c.deal_proposed}, owner='c', other=404,
         state=st_deals, roles={'a': 400}),
    Case('deal-cancel', 'post', kwargs=lambda c: {'pk': c.deal_proposed}, owner='c', other=404, state=st_deals),
    Case('deal-review', 'post', kwargs=lambda c: {'pk': c.deal_confirmed}, owner='c', owner_code=201, other=404,
         state=st_deals, roles={'a': 400}, payload={'rating': 5, 'text': 'Відмінно'}),
    Case('listing-buyers', 'get', kwargs=lambda c: {'listing_id': c.listing}, other=404,
         roles={'broker': 404, 'moderator': 404, 'staff': 404, 'admin': 200},
         forbid=lambda c: [c.u['c'].email]),

    # ---- сообщения (23-D11) ----------------------------------------------------------
    Case('msg-start', 'post', owner='c', owner_code=201, other=201, roles={'unverified': 403},
         payload=lambda c: {'listing_type': 'local', 'listing_id': c.listing_free, 'text': 'Доброго дня'},
         state=st_msgs),
    Case('msg-conversations', 'get', other=200, ids=_ids('conv')),
    Case('msg-detail', 'get', kwargs=lambda c: {'pk': c.conv}, other=404, state=st_msgs,
         roles={'broker': 404, 'moderator': 404, 'staff': 404, 'admin': 404},
         note='чужой диалог неотличим от несуществующего (как у сделок)'),
    Case('msg-detail', 'post', kwargs=lambda c: {'pk': c.conv}, owner_code=201, other=404, state=st_msgs,
         roles={'broker': 404, 'moderator': 404, 'staff': 404, 'admin': 404, 'unverified': 403},
         payload={'text': 'Відповідь'}),
    Case('msg-unread-count', 'get', other=200),

    # ---- уведомления, избранное, сохранённые поиски (23-D12, D13) --------------------
    Case('notifications-list', 'get', other=200, ids=_ids('notif')),
    Case('notifications-mark-read', 'post', other=200, state=st_notifs, payload=lambda c: {'id': c.notif},
         note='чужой id: ответ 200, но чужое is_read не меняется'),
    Case('notifications-unread-count', 'get', other=200),
    Case('favorites-list', 'get', other=200, ids=_ids('fav')),
    Case('favorites-list', 'post', owner_code=201, other=201, state=st_favs,
         payload=lambda c: {'listing_type': 'local', 'listing_id': c.listing_deal}),
    Case('favorites-list', 'delete', other=200, state=st_favs,
         payload=lambda c: {'listing_type': 'local', 'listing_id': c.listing_fav},
         note='чужой избранный лот: {deleted: false}, запись владельца цела'),
    Case('favorites-status', 'get', other=200,
         query=lambda c: f'?listing_type=local&listing_id={c.listing_fav}'),
    Case('saved-searches-list', 'get', other=200, ids=_ids('search')),
    Case('saved-searches-list', 'post', owner_code=201, other=201, state=st_searches,
         payload={'name': 'Новий', 'filters': {'make': 'Audi'}}),
    Case('saved-searches-detail', 'patch', kwargs=lambda c: {'pk': c.search}, state=st_searches,
         payload={'name': 'Чужое', 'filters': {'make': 'BMW'}}),
    Case('saved-searches-detail', 'delete', kwargs=lambda c: {'pk': c.search}, owner_code=204,
         state=st_searches),
    # GET saved-searches/<pk>/ во view не реализован (405) - строки нет; появится метод - тест полноты потребует.

    # ---- Telegram (23-D91) -----------------------------------------------------------
    Case('telegram-link-token', 'post', other=200),
    Case('telegram-unlink', 'delete', other=400, state=st_user,
         note='у постороннего Telegram не привязан: 400; привязка владельца цела'),

    # ---- контейнеры (13-S2) ----------------------------------------------------------
    Case('shipment-list', 'get', other=200, ids=_ids('shipment'), roles={'admin': 200}),
    Case('shipment-detail', 'get', kwargs=lambda c: {'pk': c.shipment}, other=404,
         roles={'broker': 404, 'moderator': 404, 'staff': 404, 'admin': 200}),
    Case('tracking-event-photo', 'get', kwargs=lambda c: {'pk': c.shipment, 'event_id': c.event}, other=404,
         roles={'broker': 404, 'moderator': 404, 'staff': 404, 'admin': 200}, note='приватное фото (1.10)'),

    # ---- объявления Украина (23-D14) -------------------------------------------------
    Case('local-listing-list', 'post', owner_code=201, other=201, payload=LISTING_PAYLOAD,
         roles={'unverified': 403}, state=st_listings),
    Case('local-listing-detail', 'patch', kwargs=lambda c: {'pk': c.listing}, other=403, state=st_listings,
         payload={'description': 'Чужое'},
         roles={'broker': 403, 'staff': 403, 'moderator': 200},
         note='решение владельца: модератор через API может править и удалять; в админке delete нет'),
    Case('local-listing-detail', 'patch', kwargs=lambda c: {'pk': c.listing_pending}, other=404, state=st_listings,
         payload={'description': 'Чужое'}, variant='pending',
         note='не-ACTIVE чужое объявление не раскрывается: 404'),
    Case('local-listing-detail', 'delete', kwargs=lambda c: {'pk': c.listing}, owner_code=204, other=403,
         state=st_listings, roles={'broker': 403, 'staff': 403, 'moderator': 204},
         note='решение владельца: модератор через API может править и удалять; в админке delete нет'),
    Case('local-listing-contact', 'get', kwargs=lambda c: {'pk': c.listing}, other=200,
         note='телефон ACTIVE-объявления виден любому вошедшему по дизайну; лимит/показ гостю - 4.5'),
    Case('local-listing-contact', 'get', kwargs=lambda c: {'pk': c.listing_pending}, owner_code=404, other=404,
         variant='pending', note='телефон не отдаётся до модерации'),
    Case('local-listing-images', 'post', kwargs=lambda c: {'pk': c.listing}, owner_code=201, other=403,
         state=st_images, fmt='multipart',
         payload=lambda c: {'images': SimpleUploadedFile('p.jpg', image_bytes(), content_type='image/jpeg')},
         roles={'broker': 403, 'staff': 403}),
    Case('local-listing-image-detail', 'patch', kwargs=lambda c: {'pk': c.listing, 'img_id': c.img2}, other=403,
         state=st_images, roles={'broker': 403, 'staff': 403}),
    Case('local-listing-image-detail', 'delete', kwargs=lambda c: {'pk': c.listing, 'img_id': c.img2},
         owner_code=204, other=403, state=st_images, roles={'broker': 403, 'staff': 403}),
    Case('local-listing-promote', 'post', kwargs=lambda c: {'pk': c.listing}, owner_code=400, other=403,
         state=st_payments, roles={'broker': 403, 'staff': 403, 'moderator': 400},
         note='пустой tariff: права пройдены (400), платёж не создаётся; 201 - local_listings.tests'),
    Case('local-my-listings', 'get', other=200, ids=_ids('listing', 'listing_pending')),

    # ---- прочее ----------------------------------------------------------------------
    Case('vin-report', 'get', kwargs=lambda c: {'vin': 'SHORT'}, owner_code=400, other=400, csrf=False,
         note='любой вошедший (дорогой внешний API; лимит expensive); короткий VIN - до вызова провайдера'),
    Case('vin-registry', 'get', kwargs=lambda c: {'vin': 'SHORT'}, owner_code=400, other=400, csrf=False,
         note='то же'),
    Case('lot-import', 'post', owner='admin', owner_code=400, other=403, payload={},
         roles={'broker': 403, 'moderator': 403, 'staff': 403, 'dealer': 403},
         note='только role=admin; пустое тело - права пройдены (400)'),
    Case('listing-create', 'post', owner='broker', owner_code=400, other=403, payload={},
         roles={'moderator': 403, 'staff': 403, 'dealer': 403, 'admin': 400},
         note='broker и admin (2.8); пустое тело - права пройдены (400)'),
    Case('liqpay-checkout', 'post', owner_code=200, other=200, state=st_payments,
         payload=lambda c: {'order_id': 'authz-checkout-1', 'amount': '10.00', 'currency': 'USD'},
         note='платёж создаётся своему user; сумма/order_id/listing_id задаёт клиент (#24) - ждёт задачу 4.1 (23-D72)'),
    Case('report-create', 'post', owner_code=201, other=201,
         payload=lambda c: {'reported_user': c.u['c'].pk, 'reason': 'spam', 'comment': ''}),
    Case('b2b-board', 'get', owner='dealer', other=403,
         roles={'broker': 403, 'moderator': 403, 'staff': 403, 'admin': 200}),

    # ---- заявки брокеру (2.1a, 2.4) --------------------------------------------------
    Case('lead-mine', 'get', other=200, ids=_lead_ids, note='только свои заявки; в ответе нет чужих id'),
    Case('lead-list', 'get', owner='broker', other=403, roles=BROKER_ROLES),
    Case('lead-export', 'get', owner='broker', other=403, roles=BROKER_ROLES, csrf=False),
    Case('lead-detail', 'get', kwargs=LEAD_URL, owner='broker', other=403, roles=BROKER_ROLES),
    Case('lead-detail', 'delete', kwargs=LEAD_URL, owner='broker', owner_code=405, other=403, state=st_leads,
         roles={'moderator': 403, 'staff': 403, 'dealer': 403, 'admin': 405},
         note='удаления заявок нет ни у кого (405); в админке - только superuser (leads.tests)'),
    Case('lead-status', 'post', kwargs=LEAD_URL, owner='broker', other=403, state=st_leads,
         payload={'status': 'in_progress'}, roles=BROKER_ROLES),
    Case('lead-take', 'post', kwargs=LEAD_URL, owner='broker', other=403, state=st_leads, roles=BROKER_ROLES),
    Case('lead-qualification', 'post', kwargs=LEAD_URL, owner='broker', other=403, state=st_leads,
         payload={'q_budget_ok': True}, roles=BROKER_ROLES),
    Case('lead-partner-status', 'post', kwargs=LEAD_URL, owner='broker', other=403, state=st_leads,
         payload={'partner_status': 'thinking'}, roles=BROKER_ROLES),
]
MATRIX_NAMES = {c.name for c in MATRIX}


# --------------------------------------------------------------------------------------
# Обход URL-конфига (тест полноты)
# --------------------------------------------------------------------------------------
def iter_named_callbacks(patterns, prefix=''):
    """(name, callback, route) для всех API-маршрутов (/api/...); name=None у безымянного маршрута
    (его ловит authz_gaps как ошибку полноты). Django-админка сюда не входит:
    у неё своя модель прав (AdminRolesTests ниже)."""
    for p in patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from iter_named_callbacks(p.url_patterns, route)
        elif isinstance(p, URLPattern) and route.startswith('api/'):
            yield p.name, p.callback, route


def _view_class(callback):
    return getattr(callback, 'cls', None)


def _effective_permissions(callback):
    cls = _view_class(callback)
    initkwargs = getattr(callback, 'initkwargs', {}) or {}
    return initkwargs.get('permission_classes', cls.permission_classes)


def _handlers(cls):
    allowed = {m.lower() for m in cls.http_method_names}
    return {m for m in HANDLER_METHODS if hasattr(cls, m) and m in allowed}


def authz_gaps(patterns, matrix=None):
    """Список проблем полноты: имя URL + что не так. Пустой список = матрица полная."""
    matrix = MATRIX if matrix is None else matrix
    by_name = {}
    for case in matrix:
        by_name.setdefault(case.name, set()).add(case.method)
    problems = []
    seen = set()
    for name, callback, route in iter_named_callbacks(patterns):
        if not name:
            problems.append(f'{route}: маршрут API без name - матрица прав не может его проверить')
            continue
        cls = _view_class(callback)
        seen.add(name)
        if name in PUBLIC:
            if cls is not None and issubclass(cls, APIView):
                perms = _effective_permissions(callback)
                if cls.get_permissions is not APIView.get_permissions:
                    problems.append(f'{name}: в белом списке публичных, но get_permissions переопределён - нужна строка матрицы')
                elif perms and not any(issubclass(p, AllowAny) for p in perms):
                    problems.append(f'{name}: в белом списке публичных, но permission_classes не AllowAny')
            continue
        if cls is None or not issubclass(cls, APIView):
            problems.append(f'{name}: не APIView и не в белом списке публичных')
            continue
        if name not in by_name:
            problems.append(f'{name}: приватный эндпоинт без строки в матрице прав')
            continue
        missing = _handlers(cls) - by_name[name] - PUBLIC_METHODS.get(name, set())
        if missing:
            problems.append(f'{name}: нет строк матрицы для методов {sorted(missing)}')
    return problems, seen


class _FakePrivateView(APIView):
    def get(self, request):
        return Response({'ok': True})


urlpatterns = [path('api/fake-private/', _FakePrivateView.as_view(), name='fake-private-endpoint')]


def reverse_any_namespace(name, kwargs):
    """reverse() по имени без пространства (b2b:, dealers: и т.п.)."""
    for ns in ('', *get_resolver().namespace_dict):
        try:
            return reverse(f'{ns}:{name}' if ns else name, kwargs=kwargs)
        except NoReverseMatch:
            continue
    raise NoReverseMatch(name)


# --------------------------------------------------------------------------------------
@override_settings(LIQPAY_PUBLIC_KEY='test_pub', LIQPAY_PRIVATE_KEY='test_priv')
class AuthzMatrixTests(CleanCacheTestCase):
    """Тесты генерируются ниже из MATRIX."""

    @classmethod
    def setUpClass(cls):
        dirs = [tempfile.mkdtemp(), tempfile.mkdtemp()]
        cls._dirs = dirs
        cls._media_override = override_settings(MEDIA_ROOT=dirs[0], PRIVATE_MEDIA_ROOT=dirs[1])
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        for d in cls._dirs:
            shutil.rmtree(d, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        s = SiteSettings.load()
        s.partner_name = 'Партнер Тест'
        s.save()
        u = {
            'a': make_user('owner.a@test.com', telegram_id=700000001),
            'b': make_user('other.b@test.com'),
            'c': make_user('party.c@test.com'),
            'e': make_user('fresh.e@test.com'),
            'unverified': make_user('unverified@test.com', verified=False),
            'staff': make_staff('staff.only@test.com'),
            'broker': make_broker('broker@test.com'),
            'moderator': make_moderator('moderator@test.com'),
            'admin': make_admin_role('admin.role@test.com'),
            'dealer': make_dealer('dealer@test.com'),
        }
        a, c_user = u['a'], u['c']
        # Владельцу поставлено удаление: чужой cancel-deletion не должен его сбросить (1.8).
        from django.utils import timezone
        CustomUser.objects.filter(pk=a.pk).update(deletion_scheduled_at=timezone.now())
        ns = SimpleNamespace(u=u)
        ns.calc = Calculation.objects.create(
            user=a, inputs_snapshot={'make': 'Toyota'}, rates_snapshot={'usd_uah': '41.5'},
            breakdown={'customs': '1000'}, total_usd='9000.50', total_uah='373520.75').pk
        shipment = Shipment.objects.create(container_no='MSCU7654321', vessel='Ever Given')
        shipment.watchers.add(a)
        photo = SimpleUploadedFile('port.jpg', image_bytes(), content_type='image/jpeg')
        ns.event = shipment.advance_status(Shipment.Status.LOADING, photo=photo).pk
        ns.shipment = shipment.pk
        ns.shop = TrustedShop.objects.create(owner=a, name='СТО Секрет', contacts='тел. 050').pk
        DealerApplication.objects.create(
            user=a, company_name='Секретна Компанія', full_name='Власник А',
            contact_phone='+380501110000')
        ns.notif = Notification.objects.create(
            user=a, type='new_message', title='Приватне сповіщення A').pk
        ns.search = SavedSearch.objects.create(user=a, name='Пошук A', filters={'make': 'Honda'}).pk

        from tests.factories import make_region_city
        region, city = make_region_city()
        ns.region, ns.city = region.pk, city.pk
        listing = make_local_listing(a)
        ns.listing = listing.pk
        ns.listing_pending = make_local_listing(a, status=LocalListing.Status.PENDING).pk
        ns.listing_fav = make_local_listing(a).pk
        ns.listing_free = make_local_listing(a).pk
        listing_confirmed = make_local_listing(a)
        listing_deal = make_local_listing(a)
        ns.listing_deal = listing_deal.pk
        LocalListingImage.objects.create(listing=listing, image='a1.jpg', is_primary=True)
        ns.img2 = LocalListingImage.objects.create(listing=listing, image='a2.jpg').pk
        ns.fav = Favorite.objects.create(user=a, local_listing_id=ns.listing_fav).pk

        for lst in (listing, listing_confirmed, listing_deal):
            get_or_create_conversation(c_user, 'local', lst.pk, 'Секретне повідомлення A-C')
        ns.conv = Conversation.objects.get(local_listing=listing).pk
        ns.deal_proposed = propose_deal(listing, a, c_user.pk).pk
        deal2 = propose_deal(listing_confirmed, a, c_user.pk)
        confirm_deal(deal2, c_user)
        ns.deal_confirmed = deal2.pk
        ns.lead = create_lead(user=a, data={
            'name': 'Іван', 'phone': '0671234567', 'contact_method': 'telegram', 'source': 'landing'}).pk
        cls.ctx = ns

    # ---- вспомогательное ---------------------------------------------------------
    def _url(self, case):
        url = reverse_any_namespace(case.name, case.kwargs(self.ctx))
        if case.query:
            url += case.query(self.ctx) if callable(case.query) else case.query
        return url

    def _payload(self, case):
        p = case.payload
        return p(self.ctx) if callable(p) else p

    def _call(self, case, client):
        return getattr(client, case.method)(self._url(case), self._payload(case), format=case.fmt)

    def _client(self, who):
        return APIClient() if who is None else auth_client(self.ctx.u[who])

    @staticmethod
    def _body(resp):
        if resp.streaming:
            return b''.join(resp.streaming_content)
        return resp.content

    def _ids_in(self, resp):
        data = resp.json()
        rows = data.get('results', data) if isinstance(data, dict) else data
        return {r['id'] for r in rows}

    def _run(self, case, who, expected, check_state=True):
        """Вызов от имени `who` с проверкой кода и неизменности данных владельца."""
        before = case.state(self.ctx) if case.state else None
        resp = self._call(case, self._client(who))
        self.assertEqual(resp.status_code, expected, f'{case.cid} as {who}: {self._body(resp)[:300]!r}')
        if case.state and check_state:
            self.assertEqual(case.state(self.ctx), before, f'{case.cid} as {who}: данные владельца изменились')
        return resp

    # ---- проверки ----------------------------------------------------------------
    def check_anon(self, case):
        self._run(case, None, 401)

    def check_other(self, case):
        resp = self._run(case, 'b', case.other)
        if resp.status_code < 400:
            if case.forbid:
                body = self._body(resp).decode()
                for marker in case.forbid(self.ctx):
                    self.assertNotIn(marker, body, f'{case.cid}: в ответе постороннему чужие данные')
            if case.ids:
                self.assertEqual(self._ids_in(resp), set(),
                                 f'{case.cid}: посторонний не должен видеть в списке ничего')

    def check_owner(self, case):
        resp = self._run_owner(case)
        if case.ids and resp.status_code < 400:
            self.assertTrue(case.ids(self.ctx) <= self._ids_in(resp), f'{case.cid}: владелец не видит свои объекты')

    def _run_owner(self, case):
        resp = self._call(case, self._client(case.owner))
        self.assertEqual(resp.status_code, case.owner_code, f'{case.cid} owner: {self._body(resp)[:300]!r}')
        return resp

    def check_role(self, case, role):
        code = case.roles[role]
        # роль с правом (2xx) вправе менять данные; отказ (>=400) - нет
        self._run(case, role, code, check_state=code >= 400)

    def check_csrf(self, case):
        """Cookie-сессия без X-CSRFToken на небезопасном методе -> 403, данные не тронуты."""
        before = case.state(self.ctx) if case.state else None
        client = APIClient(enforce_csrf_checks=True)
        token = RefreshToken.for_user(self.ctx.u[case.owner]).access_token
        client.cookies[settings.AUTH_COOKIE_ACCESS_NAME] = str(token)
        resp = self._call(case, client)
        self.assertEqual(resp.status_code, 403, f'{case.cid}: без CSRF-заголовка {self._body(resp)[:200]!r}')
        self.assertIn('CSRF', str(resp.json().get('detail', '')), f'{case.cid}: 403 не от CSRF-проверки')
        if case.state:
            self.assertEqual(case.state(self.ctx), before)
        # положительный контроль: тот же клиент с валидным токеном проходит CSRF (код владельца)
        client.cookies['csrftoken'] = 'a' * 64
        client.credentials(HTTP_X_CSRFTOKEN='a' * 64)
        ok = self._call(case, client)
        self.assertEqual(ok.status_code, case.owner_code, f'{case.cid}: с X-CSRFToken {self._body(ok)[:200]!r}')


def _install(cls, case):
    cid = case.cid
    setattr(cls, f'test_{cid}__anon', lambda self, c=case: self.check_anon(c))
    setattr(cls, f'test_{cid}__other', lambda self, c=case: self.check_other(c))
    setattr(cls, f'test_{cid}__owner', lambda self, c=case: self.check_owner(c))
    for role in case.roles:
        setattr(cls, f'test_{cid}__role_{role}', lambda self, c=case, r=role: self.check_role(c, r))
    if case.method != 'get' and case.csrf:
        setattr(cls, f'test_{cid}__no_csrf', lambda self, c=case: self.check_csrf(c))


for _case in MATRIX:
    _install(AuthzMatrixTests, _case)


class AuthzMatrixCompletenessTests(CleanCacheTestCase):
    """Новый приватный эндпоинт без строки в матрице роняет тест с именем URL."""

    def test_every_private_endpoint_is_in_matrix(self):
        problems, _ = authz_gaps(get_resolver().url_patterns)
        self.assertEqual(problems, [], 'Матрица прав неполная (tests/test_authz_matrix.py): добавьте Case')

    def test_matrix_has_no_stale_rows(self):
        _, seen = authz_gaps(get_resolver().url_patterns)
        self.assertEqual(sorted(MATRIX_NAMES - seen), [], 'Строки матрицы без эндпоинта (переименован/удалён?)')
        self.assertEqual(sorted(set(PUBLIC) - seen), [], 'В белом списке публичных есть несуществующие URL')

    def test_matrix_and_public_do_not_overlap(self):
        self.assertEqual(sorted(MATRIX_NAMES & set(PUBLIC)), [])

    def test_detects_endpoint_missing_from_matrix(self):
        """Мутационная проверка самого теста полноты: view из urlpatterns этого модуля без строки."""
        problems, _ = authz_gaps(get_resolver('tests.test_authz_matrix').url_patterns)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('fake-private-endpoint', problems[0])

    def test_detects_unnamed_api_route(self):
        """Мутация: безымянный маршрут под api/ - ошибка полноты, а не тихий пропуск."""
        problems, _ = authz_gaps([path('api/v1/unnamed-secret/', _FakePrivateView.as_view())])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('api/v1/unnamed-secret/', problems[0])
        self.assertIn('без name', problems[0])

    def test_detects_missing_method_row(self):
        rows = [c for c in MATRIX if not (c.name == 'me-trusted-shop-detail' and c.method == 'delete')]
        problems, _ = authz_gaps(get_resolver().url_patterns, rows)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('me-trusted-shop-detail', problems[0])
        self.assertIn("'delete'", problems[0])


class PricingRatesAwaiting26Tests(CleanCacheTestCase):
    """Ждёт задачу 2.6 (Q8): суммы ставок видят только staff/broker. Сейчас pricing-rates публичен."""

    @unittest.expectedFailure
    def test_rates_closed_to_anonymous(self):
        self.assertIn(APIClient().get(reverse('pricing-rates')).status_code, (401, 403))


class AdminRolesTests(CleanCacheTestCase):
    """Django-админка по ролям (Q10): у админки своя модель прав (permissions групп), в матрицу API она не входит.

    moderator: платежи, настройки сайта и заявки брокера - 403, очередь модерации - 200.
    broker: заявки - 200, остальное из этого списка - 403. Обычный пользователь - редирект на вход.
    """
    PAGES = {
        'payments': 'admin:payments_payment_changelist',
        'site_settings': 'admin:site_settings_sitesettings_changelist',
        'leads': 'admin:leads_lead_changelist',
        'moderation_queue': 'admin:local_listings_locallisting_changelist',
    }

    @classmethod
    def setUpTestData(cls):
        cls.users = {
            'buyer': make_user(),
            'staff': make_staff(),
            'moderator': make_moderator(),
            'broker': make_broker(),
        }

    def _status(self, role, page):
        self.client.force_login(self.users[role])
        return self.client.get(reverse(self.PAGES[page])).status_code

    def test_anonymous_redirected_to_login(self):
        for page, name in self.PAGES.items():
            with self.subTest(page=page):
                self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_buyer_redirected_to_login(self):
        for page in self.PAGES:
            with self.subTest(page=page):
                self.assertEqual(self._status('buyer', page), 302)

    def test_staff_without_role_gets_403_everywhere(self):
        for page in self.PAGES:
            with self.subTest(page=page):
                self.assertEqual(self._status('staff', page), 403)

    def test_moderator(self):
        expected = {'payments': 403, 'site_settings': 403, 'leads': 403, 'moderation_queue': 200}
        for page, code in expected.items():
            with self.subTest(page=page):
                self.assertEqual(self._status('moderator', page), code)

    def test_moderator_sees_pending_queue_section(self):
        """Раздел «Черга модерації» (прокси) доступен модератору: права выдаёт users.0016."""
        self.client.force_login(self.users['moderator'])
        url = reverse('admin:local_listings_pendinglocallistingproxy_changelist')
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_broker(self):
        expected = {'payments': 403, 'site_settings': 403, 'leads': 200, 'moderation_queue': 403}
        for page, code in expected.items():
            with self.subTest(page=page):
                self.assertEqual(self._status('broker', page), code)


class InfraExposureTests(CleanCacheTestCase):
    """Бриф §3, пункт 33: порты БД и Redis не открыты наружу (в compose наружу смотрит только nginx)."""

    def test_only_nginx_publishes_public_port(self):
        import re
        from pathlib import Path

        text = (Path(settings.BASE_DIR) / 'docker-compose.yml').read_text(encoding='utf-8')
        mappings = []
        in_ports = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == 'ports:':
                in_ports = True
            elif in_ports and stripped.startswith('#'):
                continue
            elif in_ports and stripped.startswith('- '):
                mappings.extend(re.findall(r'"([^"]*)"', stripped))
            else:
                in_ports = False
        self.assertTrue(mappings, 'в docker-compose.yml не найдено ни одного проброса портов')
        public = [m for m in mappings if not m.startswith('127.0.0.1:')]
        self.assertEqual(public, ['${NGINX_PORT:-80}:80'], 'наружу должен смотреть только nginx')


class ErrorTextsNotLeakedTests(CleanCacheTestCase):
    """Бриф §3, пункт 19: клиенту не уходит текст исключения (детали - в лог)."""

    SECRET = 'SECRET-INTERNAL-DETAIL'

    def test_calculator_500_has_generic_text(self):
        from unittest import mock

        payload = {
            'auction': 'copart', 'auction_price_usd': '5000', 'engine_cc': 2000,
            'fuel_type': 'petrol', 'vehicle_year': 2018, 'member_type': 'broker',
            'payment_type': 'secured', 'title_type': 'salvage',
            'us_port': 'houston', 'eu_port': 'klaipeda',
        }
        with mock.patch('pricing.views.pricing_cache.get_exchange_rates', side_effect=RuntimeError(self.SECRET)):
            resp = APIClient().post('/api/v1/pricing/calculate/', payload, format='json')
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(self.SECRET, resp.content.decode())

    def test_lot_import_400_has_generic_text(self):
        from unittest import mock

        admin = make_admin_role()
        body = {'source': 'manual', 'lot_data': {'vin': 'A' * 17}}
        with mock.patch('integrations.views.import_lot', side_effect=ValueError(self.SECRET)):
            resp = auth_client(admin).post('/api/v1/lots/import/', body, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertNotIn(self.SECRET, resp.content.decode())
