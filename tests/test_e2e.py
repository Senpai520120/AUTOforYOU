"""
Сквозные интеграционные тесты — критичные пути «конец в конец».
Все сценарии идут через реальный HTTP API (APIClient) и реальную БД (in-memory SQLite).
Запуск: python manage.py test tests.test_e2e
"""
import base64
import hashlib
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from listings.models import Listing
from payments.models import Payment
from users.models import DealerApplication
from users.services import apply_for_dealer, approve_application
from vehicles.models import Vehicle

User = get_user_model()

# ── URL-константы ──────────────────────────────────────────────────────────────

REGISTER_URL = '/api/v1/auth/register/'
TOKEN_URL    = '/api/v1/auth/token/'
PROFILE_URL  = '/api/v1/auth/profile/'
CALC_URL     = '/api/v1/pricing/calculate/'
CHECKOUT_URL = '/api/v1/payments/liqpay/checkout/'
CALLBACK_URL = '/api/v1/payments/liqpay/callback/'
B2B_URL      = '/api/v1/b2b/board/'
LISTINGS_URL = '/api/v1/listings/'
REGISTRY_URL = '/api/v1/vehicles/1HGBH41JXMN109186/registry/'
APPLY_URL    = '/api/v1/dealers/apply/'

# ── Вспомогательные функции ────────────────────────────────────────────────────

_REG_DATA = {
    'email': 'e2e_main@test.com',
    'password': 'StrongPass123!',
    'password2': 'StrongPass123!',
    'role': 'buyer',
    'agreed_to_terms': True,
}


def _make_user(email='u@test.com', **kw):
    return User.objects.create_user(email=email, password='pass123', **kw)


def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


def _make_vehicle(vin='E2EVINDEFAULT001'):
    return Vehicle.objects.create(
        make='Toyota', model='Camry', year=2020, vin=vin,
        fuel_type='petrol', engine_cc=2000, mileage_km=50000,
    )


def _make_listing(vehicle, seller, channel='retail', lst_status='in_stock'):
    return Listing.objects.create(
        vehicle=vehicle, seller=seller, price=10000, currency='USD',
        channel=channel, status=lst_status,
    )


def _liqpay_sign(data_b64: str, private_key: str) -> str:
    raw = private_key + data_b64 + private_key
    return base64.b64encode(hashlib.sha1(raw.encode()).digest()).decode()


def _build_callback(order_id: str, liqpay_status: str, private_key: str, public_key: str) -> dict:
    payload = {
        'version': 3,
        'public_key': public_key,
        'action': 'pay',
        'order_id': order_id,
        'status': liqpay_status,
        'payment_id': 99999,
        'amount': '100.00',
        'currency': 'USD',
    }
    data_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    return {'data': data_b64, 'signature': _liqpay_sign(data_b64, private_key)}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Регистрация → логин (JWT) → профиль
# ══════════════════════════════════════════════════════════════════════════════

class TestRegisterLoginProfileFlow(APITestCase):
    """Полная цепочка аутентификации: регистрация → токен → профиль."""

    def test_full_auth_chain(self):
        # Шаг 1: регистрация с согласием
        resp = self.client.post(REGISTER_URL, _REG_DATA, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        user = User.objects.get(email=_REG_DATA['email'])
        self.assertIsNotNone(user.agreed_to_terms_at, 'agreed_to_terms_at должен быть записан')

        # Шаг 2: получение JWT
        resp = self.client.post(TOKEN_URL, {
            'email': _REG_DATA['email'],
            'password': _REG_DATA['password'],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)
        access = resp.data['access']

        # Шаг 3: запрос профиля с Bearer-токеном
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        resp = self.client.get(PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['email'], _REG_DATA['email'])
        self.assertEqual(resp.data['role'], 'buyer')

    def test_register_without_consent_blocked(self):
        data = {**_REG_DATA, 'agreed_to_terms': False, 'email': 'noconsent2@test.com'}
        resp = self.client.post(REGISTER_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('agreed_to_terms', resp.data)

    def test_profile_without_token_returns_401(self):
        resp = self.client.get(PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_with_wrong_password_returns_401(self):
        self.client.post(REGISTER_URL, _REG_DATA, format='json')
        resp = self.client.post(TOKEN_URL, {
            'email': _REG_DATA['email'], 'password': 'WrongPassword!'
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Калькулятор: полный landed-cost через API (реальные seed-тарифы)
# ══════════════════════════════════════════════════════════════════════════════

class TestCalculatorAPIE2E(TestCase):
    """
    POST /api/v1/pricing/calculate/ с реальными seed-тарифами.
    Сценарий: Copart broker, бензин 2.0L 2018, $5 000.
    Ожидаем: auction_fee=$504, customs_value=$6800, is_estimate=true.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('seed_rates', verbosity=0)
        call_command('seed_auction_fees', '--clear', verbosity=0)

    def setUp(self):
        self.client = APIClient()
        self._payload = {
            'auction': 'copart',
            'auction_price_usd': '5000',
            'engine_cc': 2000,
            'fuel_type': 'petrol',
            'vehicle_year': 2018,
            'member_type': 'broker',
            'payment_type': 'secured',
            'title_type': 'salvage',
            'us_port': 'houston',
            'eu_port': 'klaipeda',
        }

    def _calc(self, **extra):
        return self.client.post(CALC_URL, {**self._payload, **extra}, format='json')

    def test_response_201_and_breakdown_present(self):
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIn('breakdown', resp.data)

    def test_all_breakdown_fields_present(self):
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        bd = resp.data['breakdown']
        required = [
            'auction_price_usd', 'auction_fee_usd', 'us_land_usd',
            'ocean_freight_usd', 'eu_to_ua_usd', 'customs_value_usd',
            'excise_eur', 'excise_uah', 'duty_usd', 'duty_uah',
            'vat_base_uah', 'vat_uah', 'pension_fund_uah',
            'customs_total_uah', 'total_usd', 'total_uah',
        ]
        for f in required:
            self.assertIn(f, bd, f'Поле {f!r} отсутствует в breakdown')

    def test_total_usd_equals_sum_of_usd_components(self):
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        bd = resp.data['breakdown']
        # total_usd = landed cost USD + import duty USD
        computed = (
            Decimal(bd['auction_price_usd'])
            + Decimal(bd['auction_fee_usd'])
            + Decimal(bd['us_land_usd'])
            + Decimal(bd['ocean_freight_usd'])
            + Decimal(bd['eu_to_ua_usd'])
            + Decimal(bd['duty_usd'])
        )
        self.assertEqual(Decimal(bd['total_usd']), computed,
                         'total_usd должен равняться сумме компонентов')

    def test_is_estimate_always_true(self):
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data.get('is_estimate'),
                        'is_estimate должен быть True для демо-тарифов')

    def test_known_auction_fee_copart_broker_5000(self):
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # buyer $300 + gate $95 + env $10 + vb $99 = $504
        self.assertEqual(
            Decimal(resp.data['breakdown']['auction_fee_usd']),
            Decimal('504.00'),
            'Auction fee Copart broker $5000 salvage = $504',
        )

    def test_known_customs_value(self):
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # auction $5000 + us_land $500 + ocean $1300 = $6800
        self.assertEqual(
            Decimal(resp.data['breakdown']['customs_value_usd']),
            Decimal('6800.00'),
        )

    def test_rates_date_in_response(self):
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('warning', resp.data)

    def test_calculator_saves_calculation_to_db(self):
        from pricing.models import Calculation
        count_before = Calculation.objects.count()
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Calculation.objects.count(), count_before + 1)

    def test_missing_required_field_returns_400(self):
        payload = dict(self._payload)
        del payload['auction_price_usd']
        resp = self.client.post(CALC_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ══════════════════════════════════════════════════════════════════════════════
# 3. LiqPay: checkout → valid callback → listing разблокирован;
#    invalid sig → отклонён; duplicate → идемпотентен
# ══════════════════════════════════════════════════════════════════════════════

_TEST_PUB  = 'test_public_key_e2e'
_TEST_PRIV = 'test_private_key_e2e'

_LIQPAY_ENV = {
    'LIQPAY_PUBLIC_KEY': _TEST_PUB,
    'LIQPAY_PRIVATE_KEY': _TEST_PRIV,
    'LIQPAY_SANDBOX': True,
}


@override_settings(**_LIQPAY_ENV)
class TestLiqPayPaymentFlow(TestCase):
    """
    E2E платёжного цикла:
    create checkout → simulate callback → verify outcome.
    Подпись формируется теми же алгоритмами, что и LiqPayClient.
    """

    def setUp(self):
        self.seller = _make_user('seller_liq@test.com')
        self.buyer  = _make_user('buyer_liq@test.com')
        self.vehicle = _make_vehicle('LIQVIN000000001')
        self.listing = _make_listing(self.vehicle, self.seller, lst_status='in_transit')
        self.buyer_client = _auth_client(self.buyer)
        self.anon = APIClient()

    def _checkout(self, order_id='e2e-order-001'):
        return self.buyer_client.post(CHECKOUT_URL, {
            'order_id': order_id,
            'amount': '100.00',
            'currency': 'USD',
            'description': 'E2E test',
            'listing_id': self.listing.pk,
        }, format='json')

    # ── Checkout ──────────────────────────────────────────────────────────────

    def test_checkout_returns_200_and_checkout_url(self):
        resp = self._checkout()
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIn('checkout_url', resp.data)
        self.assertIn('payment_id', resp.data)

    def test_checkout_creates_pending_payment(self):
        self._checkout('e2e-pending-001')
        payment = Payment.objects.get(order_id='e2e-pending-001')
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.listing, self.listing)

    def test_checkout_requires_auth(self):
        resp = self.anon.post(CHECKOUT_URL, {'order_id': 'x', 'amount': '10'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_duplicate_order_id_rejected(self):
        self._checkout('e2e-dup-001')
        resp = self._checkout('e2e-dup-001')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Callback валидный ─────────────────────────────────────────────────────

    def test_valid_callback_completes_payment(self):
        self._checkout('e2e-valid-001')
        payload = _build_callback('e2e-valid-001', 'success', _TEST_PRIV, _TEST_PUB)

        resp = self.anon.post(CALLBACK_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data.get('ok'))

        payment = Payment.objects.get(order_id='e2e-valid-001')
        self.assertEqual(payment.status, Payment.Status.COMPLETED)

    def test_valid_callback_unlocks_listing(self):
        self._checkout('e2e-unlock-001')
        payload = _build_callback('e2e-unlock-001', 'success', _TEST_PRIV, _TEST_PUB)
        self.anon.post(CALLBACK_URL, payload, format='json')

        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, 'in_stock',
                         'Листинг должен быть разблокирован после успешной оплаты')

    # ── Callback невалидный ───────────────────────────────────────────────────

    def test_invalid_signature_rejected_with_400(self):
        self._checkout('e2e-badsig-001')
        payload = _build_callback('e2e-badsig-001', 'success', 'WRONG_PRIVATE_KEY', _TEST_PUB)

        resp = self.anon.post(CALLBACK_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST,
                         'Неверная подпись должна давать 400')

    def test_invalid_signature_does_not_change_payment_status(self):
        self._checkout('e2e-badsig-002')
        payload = _build_callback('e2e-badsig-002', 'success', 'WRONG_KEY', _TEST_PUB)
        self.anon.post(CALLBACK_URL, payload, format='json')

        payment = Payment.objects.get(order_id='e2e-badsig-002')
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_invalid_signature_does_not_unlock_listing(self):
        self._checkout('e2e-badsig-003')
        payload = _build_callback('e2e-badsig-003', 'success', 'WRONG_KEY', _TEST_PUB)
        self.anon.post(CALLBACK_URL, payload, format='json')

        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, 'in_transit',
                         'Листинг не должен разблокироваться при неверной подписи')

    # ── Идемпотентность ───────────────────────────────────────────────────────

    def test_duplicate_valid_callback_idempotent(self):
        self._checkout('e2e-idem-001')
        payload = _build_callback('e2e-idem-001', 'success', _TEST_PRIV, _TEST_PUB)

        resp1 = self.anon.post(CALLBACK_URL, payload, format='json')
        resp2 = self.anon.post(CALLBACK_URL, payload, format='json')

        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        # Payment создан ровно один
        self.assertEqual(Payment.objects.filter(order_id='e2e-idem-001').count(), 1)

        # Статус: completed
        self.assertEqual(
            Payment.objects.get(order_id='e2e-idem-001').status,
            Payment.Status.COMPLETED,
        )

        # Листинг разблокирован, но не ещё раз
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, 'in_stock')

    def test_callback_missing_data_returns_400(self):
        resp = self.anon.post(CALLBACK_URL, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ══════════════════════════════════════════════════════════════════════════════
# 4. B2B-гейтинг: обычный юзер → 403/404; дилер/admin → доступ
# ══════════════════════════════════════════════════════════════════════════════

class TestB2BGatingE2E(TestCase):

    def setUp(self):
        self.seller   = _make_user('gating_seller@test.com')
        vehicle       = _make_vehicle('GATINGVIN000001')
        self.retail   = _make_listing(vehicle, self.seller, channel='retail')
        self.wholesale = _make_listing(
            _make_vehicle('GATINGVIN000002'), self.seller, channel='wholesale'
        )

    def test_anon_cannot_access_b2b_board(self):
        resp = APIClient().get(B2B_URL)
        self.assertIn(resp.status_code, (401, 403))

    def test_regular_buyer_gets_403_on_b2b_board(self):
        client = _auth_client(_make_user('gating_buyer@test.com'))
        resp = client.get(B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_buyer_gets_404_on_wholesale_detail(self):
        client = _auth_client(_make_user('gating_buyer2@test.com'))
        resp = client.get(f'{LISTINGS_URL}{self.wholesale.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND,
                         'Wholesale листинг недоступен для обычного покупателя')

    def test_regular_buyer_can_see_retail_listing(self):
        client = _auth_client(_make_user('gating_buyer3@test.com'))
        resp = client.get(f'{LISTINGS_URL}{self.retail.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_verified_dealer_accesses_b2b_board(self):
        dealer = _make_user('gating_dealer@test.com', is_verified_dealer=True, role='dealer')
        resp = _auth_client(dealer).get(B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_verified_dealer_can_see_wholesale_detail(self):
        dealer = _make_user('gating_dealer2@test.com', is_verified_dealer=True, role='dealer')
        resp = _auth_client(dealer).get(f'{LISTINGS_URL}{self.wholesale.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_admin_accesses_b2b_board(self):
        admin = User.objects.create_superuser(email='gating_admin@test.com', password='pass')
        resp = _auth_client(admin).get(B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_anon_sees_only_retail_in_catalog(self):
        anon = APIClient()
        resp = anon.get(LISTINGS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [r['id'] for r in resp.data.get('results', resp.data)]
        self.assertIn(self.retail.id, ids)
        self.assertNotIn(self.wholesale.id, ids,
                         'Wholesale не должен показываться анонимам в каталоге')


# ══════════════════════════════════════════════════════════════════════════════
# 5. Дилерская заявка → одобрение → is_verified_dealer → доступ к опту
# ══════════════════════════════════════════════════════════════════════════════

class TestDealerApplicationFlowE2E(TestCase):
    """Полный цикл: подача заявки → admin одобряет → дилер получает B2B-доступ."""

    def setUp(self):
        self.applicant = _make_user('dealer_e2e@test.com')
        self.admin     = User.objects.create_superuser(email='admin_e2e@test.com', password='pass')
        seller         = _make_user('dealer_e2e_seller@test.com')
        self.wholesale = _make_listing(
            _make_vehicle('DEALERVIN000001'), seller, channel='wholesale'
        )

    def test_full_dealer_verification_flow(self):
        # 1. Подача заявки через сервис
        app = apply_for_dealer(self.applicant, 'ТОВ Тест', 'Іван Тест', '+380991234567')
        self.assertEqual(app.status, DealerApplication.Status.PENDING)

        # 2. До одобрения — нет доступа к B2B
        client_before = _auth_client(self.applicant)
        self.assertEqual(client_before.get(B2B_URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            client_before.get(f'{LISTINGS_URL}{self.wholesale.pk}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # 3. Администратор одобряет
        approve_application(app, self.admin)

        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_verified_dealer, 'is_verified_dealer должен стать True')
        self.assertEqual(self.applicant.role, 'dealer')

        # 4. После одобрения — доступ есть (новый токен отражает изменения)
        client_after = _auth_client(self.applicant)
        self.assertEqual(client_after.get(B2B_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(
            client_after.get(f'{LISTINGS_URL}{self.wholesale.pk}/').status_code,
            status.HTTP_200_OK,
        )

    def test_dealer_application_api_flow(self):
        client = _auth_client(self.applicant)
        resp = client.post(APPLY_URL, {
            'company_name': 'ТОВ Авто',
            'full_name': 'Іван Іванов',
            'contact_phone': '+380991234567',
            'documents': 'https://drive.google.com/doc123',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], 'pending')

    def test_duplicate_application_rejected_with_409(self):
        apply_for_dealer(self.applicant, 'ТОВ 1', 'Іван', '+380')
        client = _auth_client(self.applicant)
        resp = client.post(APPLY_URL, {
            'company_name': 'ТОВ 2',
            'full_name': 'Іван',
            'contact_phone': '+380',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)


# ══════════════════════════════════════════════════════════════════════════════
# 6. Throttle: >10 запросов к /registry/ → 429
# ══════════════════════════════════════════════════════════════════════════════

class TestRegistryThrottleE2E(TestCase):
    """Платный эндпоинт /registry/ заблокирован после превышения лимита."""

    def setUp(self):
        cache.clear()
        self.user = _make_user('throttle_e2e@test.com')
        self.client = _auth_client(self.user)

    def test_after_limit_returns_429(self):
        from rest_framework.throttling import ScopedRateThrottle
        from unittest.mock import patch

        # Симулируем превышение лимита: allow_request возвращает False
        with patch.object(ScopedRateThrottle, 'allow_request', return_value=False), \
             patch.object(ScopedRateThrottle, 'wait', return_value=3600.0):
            resp = self.client.get(REGISTRY_URL)
        self.assertEqual(
            resp.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
            'После превышения лимита expensive scope должен вернуть 429',
        )

    def test_within_limit_responds_normally(self):
        from rest_framework.throttling import ScopedRateThrottle
        from unittest.mock import patch

        # В пределах лимита allow_request возвращает True
        with patch.object(ScopedRateThrottle, 'allow_request', return_value=True):
            resp = self.client.get(REGISTRY_URL)
        self.assertNotEqual(
            resp.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
            'В пределах лимита не должно быть 429',
        )

    def test_anon_gets_401_not_throttled(self):
        resp = APIClient().get(REGISTRY_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED,
                         '/registry/ требует авторизации')
