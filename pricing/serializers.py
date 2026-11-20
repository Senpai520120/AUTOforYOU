from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .calculator import EV_FUEL_TYPES
from .models import Calculation


class CalculateInputSerializer(serializers.Serializer):
    # 10.17: понятные сообщения по-украински; ценa и год обязательны, пустое поле - не 0
    auction_price_usd = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal('0'),
        error_messages={'required': 'Вкажіть ціну аукціону ($).', 'null': 'Вкажіть ціну аукціону ($).',
                        'invalid': 'Ціна аукціону має бути числом.',
                        'min_value': "Ціна аукціону не може бути від'ємною."},
    )
    # Для ЭВ/PHEV объём не нужен (пусто = 0); для ДВС/hybrid проверяет validate()
    engine_cc = serializers.IntegerField(
        min_value=0, max_value=10000, required=False, allow_null=True,
        error_messages={'invalid': "Об'єм двигуна має бути цілим числом (см³).",
                        'min_value': "Об'єм двигуна не може бути від'ємним.",
                        'max_value': "Об'єм двигуна не може перевищувати 10000 см³."},
    )
    fuel_type = serializers.ChoiceField(
        choices=['petrol', 'diesel', 'electric', 'hybrid', 'phev'],
        error_messages={'required': 'Оберіть тип палива.', 'invalid_choice': 'Оберіть тип палива зі списку.'},
    )
    vehicle_year = serializers.IntegerField(
        min_value=1900, max_value=2100,
        error_messages={'required': 'Вкажіть рік випуску.', 'null': 'Вкажіть рік випуску.',
                        'invalid': 'Рік випуску має бути числом.', 'min_value': 'Вкажіть коректний рік випуску.',
                        'max_value': 'Вкажіть коректний рік випуску.'},
    )
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

    def validate_calculation_date(self, value):
        # 2.17 (E10): будущие (ещё не вступившие) тарифы гостю не показываем. Нижней границы нет.
        if value is not None and value > timezone.localdate():
            raise serializers.ValidationError('Дата не може бути в майбутньому')
        return value

    def validate(self, attrs):
        # Акциз EV/PHEV считается по батарее (calculator.EV_FUEL_TYPES), объём двигателя нужен только ДВС/hybrid.
        is_ev = attrs['fuel_type'] in EV_FUEL_TYPES
        attrs['engine_cc'] = attrs.get('engine_cc') or 0
        if not is_ev and attrs['engine_cc'] < 1:
            raise serializers.ValidationError({'engine_cc': "Вкажіть об'єм двигуна (см³)."})
        if is_ev:
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
