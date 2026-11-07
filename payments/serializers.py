from rest_framework import serializers

from .models import Payment


class LiqPayCheckoutSerializer(serializers.Serializer):
    """
    Вхід старого загального checkout (закритий флагом PAYMENTS_LEGACY_CHECKOUT_ENABLED, задача 1.15).

    Клієнт задає тільки опис, listing_id і purpose. order_id генерує сервер (клієнтський ігнорується: перевірка
    унікальності розкривала б існування чужих замовлень), сума і валюта - серверні (payments.services.legacy_price_for),
    server_url/result_url будує build_liqpay_urls: amount, currency, order_id, server_url, result_url з запиту
    ігноруються (F2, F5). Наявність і власника листингу перевіряє view.
    """

    description = serializers.CharField(max_length=255, allow_blank=True, default='')
    listing_id = serializers.IntegerField()
    purpose = serializers.ChoiceField(choices=Payment.Purpose.choices)
