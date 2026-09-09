import logging
from datetime import timedelta

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .liqpay_client import LiqPayClient, LiqPaySignatureError
from .models import Payment
from .serializers import LiqPayCheckoutSerializer

logger = logging.getLogger(__name__)


def _apply_local_listing_promote(payment):
    """Застосувати ефект тарифу після успішної оплати просування."""
    if payment.purpose != payment.Purpose.LOCAL_LISTING_PROMOTE:
        return
    if not payment.local_listing or not payment.tariff:
        return

    from local_listings.models import LocalListing, PromotionTariff

    listing = payment.local_listing
    tariff = payment.tariff
    now = timezone.now()

    if tariff.type == PromotionTariff.TariffType.RENEW:
        base = max(listing.expires_at or now, now)
        listing.expires_at = base + timedelta(days=tariff.duration_days)
        listing.expiry_warned = False
        if listing.status == LocalListing.Status.EXPIRED:
            listing.status = LocalListing.Status.ACTIVE
        listing.save(update_fields=['expires_at', 'expiry_warned', 'status'])

    elif tariff.type == PromotionTariff.TariffType.BUMP:
        listing.bumped_at = now
        listing.save(update_fields=['bumped_at'])

    elif tariff.type == PromotionTariff.TariffType.TOP:
        base = max(listing.promoted_until or now, now)
        listing.promoted_until = base + timedelta(days=tariff.duration_days)
        listing.save(update_fields=['promoted_until'])

    logger.info('Tariff %s applied to listing %s', tariff.code, listing.pk)


@extend_schema(
    tags=['payments'],
    summary='Создать LiqPay checkout',
    description=(
        'Создаёт платёж через LiqPay и возвращает checkout URL + HTML-форму.\n\n'
        'Требует авторизации. `order_id` должен быть уникальным.\n\n'
        'Для sandbox-режима установите `LIQPAY_SANDBOX=true` в env.'
    ),
    responses={
        200: OpenApiResponse(description='checkout_url и form_data для HTML-формы'),
        400: OpenApiResponse(description='Ошибка валидации'),
    },
)
class LiqPayCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LiqPayCheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        order_id = data['order_id']
        amount = data['amount']
        currency = data['currency']
        description = data['description']
        purpose = data['purpose']
        result_url = data['result_url']
        server_url = data['server_url']

        listing = None
        if data['listing_id']:
            from listings.models import Listing
            listing = Listing.objects.get(pk=data['listing_id'])

        payment = Payment.objects.create(
            user=request.user,
            listing=listing,
            order_id=order_id,
            amount=amount,
            currency=currency,
            description=description,
            purpose=purpose,
            status=Payment.Status.PENDING,
        )

        client = LiqPayClient.from_settings()
        checkout = client.create_checkout(
            order_id=order_id,
            amount=amount,
            currency=currency,
            description=description,
            result_url=result_url,
            server_url=server_url,
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
        'Проверяет подпись (SHA1 от private_key + data + private_key).\n\n'
        'При успешной оплате обновляет Payment.status и разблокирует связанный листинг.\n\n'
        '**csrf_exempt** — LiqPay не шлёт CSRF-токен, защита — подпись.'
    ),
    responses={
        200: OpenApiResponse(description='OK'),
        400: OpenApiResponse(description='Неверная подпись или данные'),
    },
)
class LiqPayCallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        data = request.POST.get('data') or request.data.get('data', '')
        signature = request.POST.get('signature') or request.data.get('signature', '')

        if not data or not signature:
            return Response({'error': 'data и signature обязательны.'}, status=status.HTTP_400_BAD_REQUEST)

        client = LiqPayClient.from_settings()
        try:
            decoded = client.decode_callback(data, signature)
        except LiqPaySignatureError as exc:
            logger.warning('LiqPay callback: неверная подпись — %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error('LiqPay callback decode error: %s', exc)
            return Response({'error': 'Ошибка декодирования данных.'}, status=status.HTTP_400_BAD_REQUEST)

        order_id = decoded.get('order_id', '')
        liqpay_status = decoded.get('status', '')
        liqpay_payment_id = str(decoded.get('payment_id', ''))

        try:
            payment = Payment.objects.get(order_id=order_id)
        except Payment.DoesNotExist:
            logger.warning('LiqPay callback: платёж order_id=%s не найден', order_id)
            return Response({'error': f'Платёж {order_id!r} не найден.'}, status=status.HTTP_400_BAD_REQUEST)

        new_status = LiqPayClient.map_status(liqpay_status)

        # Idempotency: повторный COMPLETED-колбэк не вызывает unlock дважды
        if payment.status == Payment.Status.COMPLETED and new_status == Payment.Status.COMPLETED:
            logger.info('LiqPay callback: платёж %s уже завершён, дубликат проигнорирован', order_id)
            return Response({'ok': True, 'status': payment.status})

        payment.liqpay_status = liqpay_status
        payment.liqpay_payment_id = liqpay_payment_id
        payment.liqpay_raw = decoded
        payment.status = new_status
        payment.save(update_fields=['status', 'liqpay_status', 'liqpay_payment_id', 'liqpay_raw', 'updated_at'])

        if payment.status == Payment.Status.COMPLETED:
            payment.unlock_listing()
            _apply_local_listing_promote(payment)
            logger.info('LiqPay: payment %s completed', order_id)

        return Response({'ok': True, 'status': payment.status})
