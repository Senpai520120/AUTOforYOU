from decimal import Decimal

from rest_framework import serializers

from .models import Payment

CURRENCIES = ['UAH', 'USD', 'EUR']


class LiqPayCheckoutSerializer(serializers.Serializer):
    """
    Валідація вхідних даних чекауту.

    Раніше в'ю читала order_id, amount, currency, listing_id і purpose прямо
    з request.data без будь-якої перевірки: нечислова сума давала 500 замість
    400, а неіснуючий листинг мовчки створював платіж у нікуди.

    Сума як і раніше приходить від клієнта — для purpose listing_unlock і
    listing_vip серверного прайсу не існує. Це окреме питання (#24), тут
    закривається тільки валідація вводу.
    """

    order_id = serializers.CharField(max_length=100)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.01'),
    )
    currency = serializers.ChoiceField(choices=CURRENCIES, default='USD')
    description = serializers.CharField(max_length=255, allow_blank=True, default='')
    listing_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    purpose = serializers.ChoiceField(
        choices=Payment.Purpose.choices, default=Payment.Purpose.OTHER,
    )
    result_url = serializers.URLField(required=False, allow_blank=True, default='')
    server_url = serializers.URLField(required=False, allow_blank=True, default='')

    def validate_order_id(self, value):
        if Payment.objects.filter(order_id=value).exists():
            raise serializers.ValidationError(f'Платёж с order_id={value!r} уже существует.')
        return value

    def validate_listing_id(self, value):
        if value is None:
            return value
        from listings.models import Listing

        if not Listing.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f'Листинг #{value} не найден.')
        return value
