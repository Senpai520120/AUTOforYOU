"""
Сквозные интеграционные тесты — критичные пути «конец в конец».
Все сценарии идут через реальный HTTP API (APIClient) и реальную БД
(БД теста: SQLite локально, PostgreSQL в CI).
Точечные проверки (B2B-гейтинг, wholesale, согласие, 409, registry 401/429)
живут в тестах своих приложений: users, listings, integrations.
Запуск: python manage.py test tests.test_e2e
"""
import base64
import hashlib
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from payments.models import Payment
from users.models import DealerApplication
from users.services import apply_for_dealer, approve_application
from tests.base import CleanCacheTestCase
from tests.factories import auth_client, make_listing, make_staff, make_user, make_vehicle

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
APPLY_URL    = '/api/v1/dealers/apply/'

# ── Вспомогательные функции ────────────────────────────────────────────────────

_REG_DATA = {
    'email': 'e2e_main@test.com',
    'password': 'StrongPass123!',
    'password2': 'StrongPass123!',
    'role': 'buyer',
    'agreed_to_terms': True,
    'confirmed_age_18': True,
}


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
        self.assertEqual(resp.data, {'ok': True})  # токены только в httpOnly-cookie (1.4)
        self.assertIn('access', resp.cookies)

        # Шаг 3: запрос профиля по cookie
        resp = self.client.get(PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['email'], _REG_DATA['email'])
        self.assertEqual(resp.data['role'], 'buyer')

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

class TestCalculatorAPIE2E(CleanCacheTestCase):
    """
    POST /api/v1/pricing/calculate/ с реальными seed-тарифами.
    Сценарий: Copart broker, бензин 2.0L 2018, $5 000.
    Ожидаем: auction_fee=$504, customs_value=$6800, is_estimate=true.
    """

    @classmethod
    def setUpTestData(cls):
        call_command('seed_rates', verbosity=0)
        call_command('seed_auction_fees', '--clear', verbosity=0)

    def setUp(self):
        super().setUp()
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

    def test_exchange_rate_date_in_response(self):
        from datetime import date
        resp = self._calc()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Дата курса — ISO YYYY-MM-DD (date.fromisoformat падает на другом формате).
        rate_date = resp.data['exchange_rate_date']
        self.assertRegex(rate_date, r'^\d{4}-\d{2}-\d{2}$')
        date.fromisoformat(rate_date)
        # Дата тарифов, зафиксированная в замороженном снимке расчёта (в БД, не в ответе).
        from pricing.models import Calculation
        rates_date = Calculation.objects.get(pk=resp.data['calculation_id']).rates_snapshot['rates_date']
        self.assertRegex(rates_date, r'^\d{4}-\d{2}-\d{2}$')
        date.fromisoformat(rates_date)

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
        self.seller = make_user('seller_liq@test.com')
        self.buyer  = make_user('buyer_liq@test.com')
        self.vehicle = make_vehicle(vin='LIQVIN000000001')
        self.listing = make_listing(self.vehicle, self.seller, status='in_transit')
        self.buyer_client = auth_client(self.buyer)
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
# 4. Дилерская заявка → одобрение → is_verified_dealer → доступ к опту
# ══════════════════════════════════════════════════════════════════════════════

class TestDealerApplicationFlowE2E(TestCase):
    """Полный цикл: подача заявки → admin одобряет → дилер получает B2B-доступ."""

    def setUp(self):
        self.applicant = make_user('dealer_e2e@test.com')
        self.admin     = make_staff('admin_e2e@test.com', superuser=True)
        seller         = make_user('dealer_e2e_seller@test.com')
        self.wholesale = make_listing(
            make_vehicle(vin='DEALERVIN000001'), seller, channel='wholesale'
        )

    def test_full_dealer_verification_flow(self):
        # 1. Подача заявки через сервис
        app = apply_for_dealer(self.applicant, 'ТОВ Тест', 'Іван Тест', '+380991234567')
        self.assertEqual(app.status, DealerApplication.Status.PENDING)

        # 2. До одобрения — нет доступа к B2B
        client_before = auth_client(self.applicant)
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
        client_after = auth_client(self.applicant)
        self.assertEqual(client_after.get(B2B_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(
            client_after.get(f'{LISTINGS_URL}{self.wholesale.pk}/').status_code,
            status.HTTP_200_OK,
        )

    def test_dealer_application_api_flow(self):
        client = auth_client(self.applicant)
        resp = client.post(APPLY_URL, {
            'company_name': 'ТОВ Авто',
            'full_name': 'Іван Іванов',
            'contact_phone': '+380991234567',
            'documents': 'https://drive.google.com/doc123',
            'agreed_to_processing': True, 'confirmed_age_18': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], 'pending')
