import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.c2c import payments_enabled

from .liqpay_client import LiqPayNotConfigured, LiqPaySignatureError
from .models import Payment
from .providers import get_payment_provider, unavailable_response
from .serializers import LiqPayCheckoutSerializer
from .services import apply_payment_effect, build_liqpay_urls, legacy_price_for

logger = logging.getLogger(__name__)

CALLBACK_NOT_CONFIGURED_DETAIL = 'Оплата не налаштована'
INVALID_BODY = {'detail': 'invalid'}  # не раскрывает причину отказа (подпись, формат) и order_id


def _callback_matches(payment, decoded) -> bool:
    """F4: action, currency и amount из подписанного callback совпадают с Payment."""
    if decoded.get('action') != 'pay' or decoded.get('currency') != payment.currency:
        return False
    try:
        return Decimal(str(decoded.get('amount'))) == payment.amount
    except InvalidOperation:
        return False


@extend_schema(
    tags=['payments'],
    summary='Создать LiqPay checkout (старый, закрыт флагом)',
    description=(
        'Старый общий checkout. Закрыт `PAYMENTS_LEGACY_CHECKOUT_ENABLED=false` (404). При включённом флаге: '
        'листинг только свой, цена и валюта определяются сервером по `purpose` (сейчас цен нет, ответ 400), '
        '`amount`, `currency`, `server_url`, `result_url` из запроса игнорируются.\n\n'
        'Режим задаёт `LIQPAY_MODE` (auto/real/sandbox/off); без ключей ответ 503.'
    ),
    responses={
        200: OpenApiResponse(description='checkout_url и form_data для HTML-формы'),
        400: OpenApiResponse(description='Ошибка валидации или purpose без серверной цены'),
        404: OpenApiResponse(description='Checkout закрыт флагом, листинг не найден или чужой'),
        503: OpenApiResponse(description='Оплата не налаштована или выключена (LIQPAY_MODE)'),
    },
)
class LiqPayCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # F2: старый checkout (сумма от клиента) закрыт флагом; Payment не создаётся. 6.7: PAYMENTS_ENABLED тоже закрывает.
        if not settings.PAYMENTS_LEGACY_CHECKOUT_ENABLED or not payments_enabled():
            raise Http404
        serializer = LiqPayCheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        # Листинг только свой; чужой и несуществующий неразличимы (404).
        from listings.models import Listing
        listing = Listing.objects.filter(pk=data['listing_id'], seller=request.user).first()
        if listing is None:
            raise Http404

        price = legacy_price_for(data['purpose'])
        if price is None:
            return Response({'purpose': ['Для цього призначення немає серверної ціни.']},
                            status=status.HTTP_400_BAD_REQUEST)
        amount, currency = price

        provider = get_payment_provider()
        if not provider.is_configured():
            return unavailable_response()

        order_id = f'legacy-{uuid.uuid4().hex}'
        description = data['description']
        payment = Payment.objects.create(
            user=request.user,
            listing=listing,
            order_id=order_id,
            amount=amount,
            currency=currency,
            description=description,
            purpose=data['purpose'],
            status=Payment.Status.PENDING,
        )

        checkout = provider.create_checkout(
            order_id=order_id,
            amount=amount,
            currency=currency,
            description=description,
            **build_liqpay_urls(order_id),
        )

        return Response({
            'payment_id': payment.pk,
            'order_id': order_id,
            'checkout_url': checkout['checkout_url'],
            'form_data': checkout['form_data'],
            'sandbox': checkout['sandbox'],
        })


@method_decorator(csrf_exempt, name='dispatch')
@extend_schema(
    tags=['payments'],
    summary='LiqPay webhook (callback)',
    description=(
        'Принимает POST-колбэк от LiqPay после оплаты.\n\n'
        'Проверяет подпись (SHA1 от private_key + data + private_key, сравнение `hmac.compare_digest`).\n\n'
        'Платёж блокируется на время обработки; `amount`, `currency`, `action` сверяются с заказом '
        '(расхождение - `failed`). `completed` - конечный статус, эффект применяется один раз.\n\n'
        '**csrf_exempt** — LiqPay не шлёт CSRF-токен, защита — подпись.'
    ),
    responses={
        200: OpenApiResponse(description='OK; неизвестный order_id -> {"ok": false}'),
        400: OpenApiResponse(description='{"detail": "invalid"}: неверная подпись или данные'),
        503: OpenApiResponse(description='Оплата не налаштована (нет ключа или LIQPAY_MODE=off)'),
    },
)
class LiqPayCallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        data = request.POST.get('data') or request.data.get('data', '')
        signature = request.POST.get('signature') or request.data.get('signature', '')

        # 6.7 (минимум от 06-S1): без настроенного провайдера подпись проверить нечем - 503 до любого обращения к БД.
        # Callback флагами C2C_*/PAYMENTS_ENABLED не закрывается (Q17).
        provider = get_payment_provider()
        if not provider.is_configured():
            return Response({'detail': CALLBACK_NOT_CONFIGURED_DETAIL}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if not data or not signature:
            return Response(INVALID_BODY, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded = provider.decode_callback(data, signature)
        except LiqPayNotConfigured:
            return Response({'detail': CALLBACK_NOT_CONFIGURED_DETAIL}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except LiqPaySignatureError as exc:
            logger.warning('LiqPay callback: неверная подпись (%s): %s', type(exc).__name__, exc)
            return Response(INVALID_BODY, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error('LiqPay callback decode error (%s): %s', type(exc).__name__, exc)
            return Response(INVALID_BODY, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(decoded, dict):
            return Response(INVALID_BODY, status=status.HTTP_400_BAD_REQUEST)

        order_id = str(decoded.get('order_id', ''))
        with transaction.atomic():
            # F3: строка платежа заблокирована до конца обработки, параллельный callback ждёт её.
            payment = Payment.objects.select_for_update().filter(order_id=order_id).first()
            if payment is None:
                logger.warning('LiqPay callback: платёж не найден')
                return Response({'ok': False})
            return self._process(provider, payment, decoded)

    @staticmethod
    def _process(provider, payment, decoded):
        S = Payment.Status
        liqpay_status = str(decoded.get('status', ''))
        new_status = provider.map_status(liqpay_status)

        # F3: COMPLETED - конечный статус (допустим только возврат), REVERSED - конечный.
        # Откат эффекта при возврате - задача 4.1.
        if payment.status == S.REVERSED or (payment.status == S.COMPLETED and new_status != S.REVERSED):
            logger.info('LiqPay callback: платёж %s уже %s, статус %s проигнорирован',
                        payment.pk, payment.status, new_status)
            return Response({'ok': True, 'status': payment.status})

        if not _callback_matches(payment, decoded):
            logger.warning('LiqPay callback: платёж %s - action/amount/currency не совпали с заказом', payment.pk)
            payment.liqpay_raw = decoded
            payment.status = S.FAILED
            payment.save(update_fields=['status', 'liqpay_raw', 'updated_at'])
            return Response({'ok': True, 'status': payment.status})

        payment.liqpay_status = liqpay_status
        payment.liqpay_payment_id = str(decoded.get('payment_id', ''))
        payment.liqpay_raw = decoded
        payment.status = new_status
        payment.save(update_fields=['status', 'liqpay_status', 'liqpay_payment_id', 'liqpay_raw', 'updated_at'])

        if payment.status == S.COMPLETED and apply_payment_effect(payment):
            logger.info('LiqPay: payment %s completed', payment.pk)

        return Response({'ok': True, 'status': payment.status})

