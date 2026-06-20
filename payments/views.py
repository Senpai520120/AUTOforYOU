import logging

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .liqpay_client import LiqPayClient, LiqPaySignatureError
from .models import Payment

logger = logging.getLogger(__name__)


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
        data = request.data
        order_id = data.get('order_id')
        amount = data.get('amount')
        currency = data.get('currency', 'USD')
        description = data.get('description', '')
        listing_id = data.get('listing_id')
        purpose = data.get('purpose', Payment.Purpose.OTHER)
        result_url = data.get('result_url', '')
        server_url = data.get('server_url', '')

        if not order_id or not amount:
            return Response({'error': 'order_id и amount обязательны.'}, status=status.HTTP_400_BAD_REQUEST)

        if Payment.objects.filter(order_id=order_id).exists():
            return Response({'error': f'Платёж с order_id={order_id!r} уже существует.'}, status=status.HTTP_400_BAD_REQUEST)

        listing = None
        if listing_id:
            from listings.models import Listing
            try:
                listing = Listing.objects.get(pk=listing_id)
            except Listing.DoesNotExist:
                return Response({'error': f'Листинг #{listing_id} не найден.'}, status=status.HTTP_400_BAD_REQUEST)

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

        payment.liqpay_status = liqpay_status
        payment.liqpay_payment_id = liqpay_payment_id
        payment.liqpay_raw = decoded
        payment.status = LiqPayClient.map_status(liqpay_status)
        payment.save(update_fields=['status', 'liqpay_status', 'liqpay_payment_id', 'liqpay_raw', 'updated_at'])

        if payment.status == Payment.Status.COMPLETED:
            payment.unlock_listing()
            logger.info('LiqPay: payment %s completed, listing unlocked', order_id)

        return Response({'ok': True, 'status': payment.status})
