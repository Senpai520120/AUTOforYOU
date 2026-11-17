"""Общие фабрики тестовых данных (задача 0.6, 13-Q12).

Простые функции без сторонних зависимостей. Новые локальные `_make_user` /
`_auth_client` в тестах не заводить — использовать этот модуль.
"""
import itertools

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from listings.models import Listing
from local_listings.models import City, LocalListing, Region
from vehicles.models import Vehicle

TEST_PASSWORD = 'testpass123'

_counter = itertools.count(1)


def _next():
    return next(_counter)


def make_user(email=None, *, verified=True, password=TEST_PASSWORD, **kw):
    """Обычный пользователь. По умолчанию email подтверждён (verified=False — неподтверждённый)."""
    if email is None:
        email = f'user{_next()}@test.com'
    kw.setdefault('is_email_verified', verified)
    return get_user_model().objects.create_user(email=email, password=password, **kw)


def make_dealer(email=None, **kw):
    """Верифицированный дилер (B2B-доступ)."""
    kw.setdefault('role', 'dealer')
    kw.setdefault('is_verified_dealer', True)
    return make_user(email, **kw)


def make_staff(email=None, superuser=False, **kw):
    """Сотрудник (is_staff). superuser=True — ещё и суперпользователь."""
    kw.setdefault('is_staff', True)
    if superuser:
        kw['is_superuser'] = True
    return make_user(email, **kw)


def make_broker(email=None, **kw):
    """Брокер: role + группа «Брокери» + is_staff (как действие админки)."""
    from users.services import assign_role
    user = make_user(email, **kw)
    assign_role(user, 'broker')
    return user


def make_moderator(email=None, **kw):
    """Модератор: role + группа «Модератори» (право moderate_locallisting) + is_staff."""
    from users.services import assign_role
    user = make_user(email, **kw)
    assign_role(user, 'moderator')
    return user


def make_admin_role(email=None, **kw):
    """Администратор по роли: role='admin' + is_staff (без суперправ)."""
    kw.setdefault('role', 'admin')
    kw.setdefault('is_staff', True)
    return make_user(email, **kw)


def auth_client(user) -> APIClient:
    """APIClient с JWT-заголовком пользователя."""
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def make_region_city():
    """(Region, City) с фиксированными slug — повторный вызов возвращает те же объекты."""
    region, _ = Region.objects.get_or_create(
        slug='test-region', defaults={'name': 'Тестова область'},
    )
    city, _ = City.objects.get_or_create(
        region=region, slug='test-city', defaults={'name': 'Тестове місто'},
    )
    return region, city


def make_local_listing(owner, status=LocalListing.Status.ACTIVE, region=None, city=None, **kw):
    if region is None or city is None:
        region, city = make_region_city()
    defaults = dict(
        make='Toyota', model='Camry', year=2020, mileage_km=50000,
        fuel_type='petrol', transmission='auto', body_type='sedan',
        price='500000', currency='UAH', price_type='fixed',
        region=region, city=city, agreed_to_rules=True,
    )
    defaults.update(kw)
    return LocalListing.objects.create(owner=owner, status=status, **defaults)


def make_vehicle(**kw):
    n = _next()
    defaults = dict(
        make='Toyota', model='Camry', year=2020, vin=f'FACTVIN{n:010d}',
        fuel_type='petrol', engine_cc=2000, mileage_km=50000,
    )
    defaults.update(kw)
    return Vehicle.objects.create(**defaults)


def make_listing(vehicle, seller, channel='retail', status='in_stock', **kw):
    defaults = dict(price=10000, currency='USD')
    defaults.update(kw)
    return Listing.objects.create(
        vehicle=vehicle, seller=seller, channel=channel, status=status, **defaults,
    )


def make_lead(**kw):
    from django.utils import timezone

    from leads.models import Lead
    defaults = dict(name='Тест', phone='+380501234567', consent_at=timezone.now(), partner_consent_at=timezone.now(),
                    source='calculator')
    defaults.update(kw)
    return Lead.objects.create(**defaults)


def nhtsa_response(**fields):
    """Мок ответа NHTSA vPIC (DecodeVinValuesExtended) для `patch('httpx.get')`. ErrorCode по умолчанию '0'."""
    from unittest.mock import MagicMock

    row = {'ErrorCode': '0', 'Make': 'HONDA', 'Model': 'Civic', 'ModelYear': '2021'}
    row.update(fields)
    resp = MagicMock()
    resp.json.return_value = {'Results': [row]}
    resp.raise_for_status = MagicMock()
    return resp
