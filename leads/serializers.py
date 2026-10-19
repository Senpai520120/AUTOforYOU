import re

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from listings.models import Listing
from listings.permissions import can_view_wholesale
from pricing.models import Calculation

from .models import ContactMethod, Lead, LeadSource, LeadStatus, NeededWhen
from .validators import clean_attribution, normalize_ua_phone

# Чужой и несуществующий объект неразличимы: нет утечки существования.
_INVALID_CALCULATION = 'Розрахунок не знайдено.'
_INVALID_LISTING = 'Лот не знайдено.'
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_CONTROL_MULTILINE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')  # comment: tab, LF, CR allowed
_CONTROL_MESSAGE = 'Недопустимі керуючі символи.'


class LeadCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    contact_method = serializers.ChoiceField(choices=ContactMethod.choices, required=False, allow_blank=True)
    contact_handle = serializers.CharField(max_length=64, required=False, allow_blank=True)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    source = serializers.ChoiceField(choices=LeadSource.choices, required=False)
    landing_slug = serializers.CharField(max_length=100, required=False, allow_blank=True)
    calculation_id = serializers.IntegerField(required=False, allow_null=True)
    listing_id = serializers.IntegerField(required=False, allow_null=True)
    budget_usd = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False, allow_null=True,
    )
    needed_when = serializers.ChoiceField(choices=NeededWhen.choices, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    vehicle_label = serializers.CharField(max_length=150, required=False, allow_blank=True)
    # Атрибуция нормализуется тихо (clean_attribution): 400 из-за неё невозможен.
    utm = serializers.JSONField(required=False, write_only=True)
    referrer = serializers.JSONField(required=False, write_only=True)
    entry_page_url = serializers.JSONField(required=False, write_only=True)
    page_url = serializers.JSONField(required=False, write_only=True)
    consent = serializers.BooleanField()
    partner_consent = serializers.BooleanField()
    # Honeypot и капчу обрабатывает view; поля здесь только для схемы.
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)
    captcha_token = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_name(self, value):
        if _CONTROL.search(value):
            raise serializers.ValidationError(_CONTROL_MESSAGE)
        return value

    def validate_contact_handle(self, value):
        if _CONTROL.search(value):
            raise serializers.ValidationError(_CONTROL_MESSAGE)
        return value

    def validate_comment(self, value):
        if _CONTROL_MULTILINE.search(value):
            raise serializers.ValidationError(_CONTROL_MESSAGE)
        return value

    def validate_phone(self, value):
        try:
            return normalize_ua_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)

    def validate_consent(self, value):
        if value is not True:
            raise serializers.ValidationError('Потрібна згода на обробку персональних даних.')
        return value

    def validate_partner_consent(self, value):
        if value is not True:
            raise serializers.ValidationError('Потрібна згода на передачу даних партнеру.')
        return value

    def validate(self, attrs):
        user = getattr(self.context.get('request'), 'user', None)
        authenticated = bool(user and user.is_authenticated)

        calculation = listing = None
        calc_id = attrs.get('calculation_id')
        listing_id = attrs.get('listing_id')
        if calc_id is not None:
            calculation = Calculation.objects.filter(pk=calc_id).first()
            if calculation is None or (
                    calculation.user_id is not None and (not authenticated or calculation.user_id != user.pk)):
                raise serializers.ValidationError({'calculation_id': _INVALID_CALCULATION})
        if listing_id is not None:
            listing = Listing.objects.select_related('vehicle').filter(pk=listing_id).first()
            if listing is None or (listing.channel == Listing.Channel.WHOLESALE and not can_view_wholesale(user)):
                raise serializers.ValidationError({'listing_id': _INVALID_LISTING})

        source = attrs.get('source')
        if source is None:
            if calculation is not None:
                source = LeadSource.CALCULATOR
            elif listing is not None:
                source = LeadSource.LISTING
            else:
                raise serializers.ValidationError({'source': 'Вкажіть точку входу заявки.'})
        if source == LeadSource.CALCULATOR and calculation is None:
            raise serializers.ValidationError({'calculation_id': 'Потрібен розрахунок.'})
        if source == LeadSource.LISTING and listing is None:
            raise serializers.ValidationError({'listing_id': 'Потрібен лот.'})
        attrs['source'] = source
        attrs['calculation'] = calculation
        attrs['listing'] = listing
        attrs.update(clean_attribution(attrs))
        return attrs


class LeadCreatedSerializer(serializers.ModelSerializer):
    """Ответ на создание: без ПДн."""

    class Meta:
        model = Lead
        fields = ['public_id', 'status', 'created_at']
        read_only_fields = fields


class LeadMineSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    listing_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Lead
        fields = [
            'id', 'public_id', 'status', 'status_display', 'source', 'vehicle_label',
            'total_usd', 'total_uah', 'listing_id', 'created_at',
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Служебный spam клиенту не показываем: для него это отказ.
        if data['status'] == LeadStatus.SPAM:
            data['status'] = LeadStatus.REJECTED.value
            data['status_display'] = LeadStatus.REJECTED.label
        return data
