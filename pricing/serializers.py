from decimal import Decimal

from rest_framework import serializers

from .models import Calculation


class CalculateInputSerializer(serializers.Serializer):
    auction_price_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0'))
    engine_cc = serializers.IntegerField(min_value=0, max_value=10000)
    fuel_type = serializers.ChoiceField(choices=['petrol', 'diesel', 'electric', 'hybrid', 'phev'])
    vehicle_year = serializers.IntegerField(min_value=1900, max_value=2100)
    # Ёмкость батареи в кВт·ч (2.5, 02-Q3): обязательна и > 0 для electric/phev, для ДВС не нужна
    battery_capacity_kwh = serializers.DecimalField(
        max_digits=5, decimal_places=1, min_value=Decimal('0'), max_value=Decimal('300'),
        required=False, allow_null=True,
    )
    auction = serializers.ChoiceField(choices=['copart', 'iaai'], default='copart')
    # Тип участника / оплаты / титула (тиер buyer fee). Не передано - дефолт из pricing.views.FORM_DEFAULTS (02-C11).
    member_type = serializers.ChoiceField(choices=['public', 'licensed', 'broker'], required=False)
    payment_type = serializers.ChoiceField(choices=['secured', 'unsecured'], required=False)
    title_type = serializers.ChoiceField(choices=['clean', 'salvage', 'any'], required=False)
    auction_location = serializers.CharField(max_length=100, default='general')
    us_port = serializers.CharField(max_length=50, default='houston')
    # Порт ЕС - данные (02-C4): наличие маршрута проверяет select_rates (нет активного фрахта/доставки - 422).
    eu_port = serializers.CharField(max_length=20, default='klaipeda')
    # Доставка по Украине (2.7): id из /rates/ ua_delivery_rates; не указано - «уточнюється менеджером».
    ua_delivery_rate = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Дата оформления таможни (YYYY-MM-DD). По ней берётся курс НБУ.
    # Если не указана - сегодня. Курс берётся последний не позже этой даты; курса «из будущего» нет (02-Q5).
    calculation_date = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if attrs['fuel_type'] in ('electric', 'phev'):
            kwh = attrs.get('battery_capacity_kwh')
            if kwh is None or kwh <= 0:
                raise serializers.ValidationError({'battery_capacity_kwh': 'Вкажіть ємність батареї (кВт·год).'})
        else:
            attrs['battery_capacity_kwh'] = None
        return attrs


class CalculationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Calculation
        fields = ('id', 'user', 'inputs_snapshot', 'rates_snapshot', 'breakdown',
                  'total_usd', 'total_uah', 'is_estimate', 'created_at')
        read_only_fields = fields
