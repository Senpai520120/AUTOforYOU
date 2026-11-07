import re

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.modules import module_enabled
from landings.services import get_published_page
from listings.models import Listing
from listings.permissions import can_view_wholesale
from pricing.models import Calculation

from .models import ContactMethod, Lead, LeadSource, LeadStatus, LeadStatusChange, NeededWhen, PartnerStatus
from .services import allowed_transitions
from .validators import clean_attribution, normalize_ua_phone

# Чужой и несуществующий объект неразличимы: нет утечки существования.
_INVALID_CALCULATION = 'Розрахунок не знайдено.'
_INVALID_LISTING = 'Лот не знайдено.'
_INVALID_LANDING = 'Сторінку не знайдено.'
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
            if (
                listing is None
                or not module_enabled('lots')
                or (
                    listing.channel == Listing.Channel.WHOLESALE
                    and not (module_enabled('b2b') and can_view_wholesale(user))
                )
            ):
                raise serializers.ValidationError({'listing_id': _INVALID_LISTING})

        landing = None
        slug = (attrs.get('landing_slug') or '').strip()
        if slug:
            landing = get_published_page(slug)
            if landing is None:
                raise serializers.ValidationError({'landing_slug': _INVALID_LANDING})
            if calculation is not None or listing is not None:
                raise serializers.ValidationError({'landing_slug': 'Не поєднується з розрахунком чи лотом.'})
            attrs['source'] = LeadSource.LANDING  # точка входу задана сторінкою, а не клієнтом
            attrs['landing_slug'] = slug
            attrs['entry_page_url'] = f'/prigon/{slug}'
        attrs['landing'] = landing

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


def staff_ref(user, request) -> dict | None:
    """Сотрудник для кабинета: отображаемое имя; email только себе и admin-роли."""
    if user is None:
        return None
    ref = {'id': user.pk, 'name': f'{user.first_name} {user.last_name}'.strip() or f'Брокер #{user.pk}'}
    viewer = getattr(request, 'user', None)
    if viewer is not None and viewer.is_authenticated and (viewer.pk == user.pk or viewer.is_admin_role):
        ref['email'] = user.email
    return ref


class _AssigneeMixin:
    def get_assigned_to(self, obj) -> dict | None:
        return staff_ref(obj.assigned_to, self.context.get('request'))


class BrokerLeadListSerializer(_AssigneeMixin, serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    partner_status_display = serializers.CharField(source='get_partner_status_display', read_only=True)
    qualification_display = serializers.CharField(source='get_qualification_display', read_only=True)
    utm_source = serializers.SerializerMethodField()
    car = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            'id', 'public_id', 'created_at', 'name', 'phone', 'contact_method', 'status', 'status_display',
            'partner_status', 'partner_status_display', 'total_usd', 'total_uah', 'source', 'source_display',
            'utm_source', 'first_response_at', 'assigned_to', 'car', 'qualification', 'qualification_display',
        ]
        read_only_fields = fields

    def get_utm_source(self, obj) -> str:
        value = (obj.utm or {}).get('source')
        return value if isinstance(value, str) else ''

    def get_car(self, obj) -> str:
        if obj.vehicle_label:
            return obj.vehicle_label
        inputs = (obj.calculation_snapshot or {}).get('inputs_snapshot') or {}
        return ' '.join(str(inputs[k]) for k in ('make', 'model', 'year') if inputs.get(k))


class BrokerStatusChangeSerializer(serializers.ModelSerializer):
    from_status_display = serializers.SerializerMethodField()
    to_status_display = serializers.SerializerMethodField()
    changed_by = serializers.SerializerMethodField()

    class Meta:
        model = LeadStatusChange
        fields = ['id', 'from_status', 'from_status_display', 'to_status', 'to_status_display',
                  'changed_by', 'note', 'created_at']
        read_only_fields = fields

    def get_from_status_display(self, obj) -> str:
        return LeadStatus(obj.from_status).label if obj.from_status in LeadStatus.values else ''

    def get_to_status_display(self, obj) -> str:
        return LeadStatus(obj.to_status).label if obj.to_status in LeadStatus.values else obj.to_status

    def get_changed_by(self, obj) -> dict | None:
        return staff_ref(obj.changed_by, self.context.get('request')) if obj.changed_by_id else None


class BrokerLeadDetailSerializer(BrokerLeadListSerializer):
    listing = serializers.SerializerMethodField()
    history = BrokerStatusChangeSerializer(source='status_changes', many=True, read_only=True)
    allowed_transitions = serializers.SerializerMethodField()
    needed_when_display = serializers.CharField(source='get_needed_when_display', read_only=True)
    contact_method_display = serializers.CharField(source='get_contact_method_display', read_only=True)

    class Meta(BrokerLeadListSerializer.Meta):
        fields = BrokerLeadListSerializer.Meta.fields + [
            'email', 'contact_method_display', 'contact_handle', 'comment', 'budget_usd', 'needed_when',
            'needed_when_display', 'city', 'utm', 'referrer', 'entry_page_url', 'page_url',
            'calculation_snapshot', 'listing', 'history', 'allowed_transitions', 'partner_name', 'updated_at',
            'q_budget_ok', 'q_term_ok', 'q_knows_repair', 'q_ready_deposit', 'attribution_until',
        ]
        read_only_fields = fields

    def get_listing(self, obj) -> dict | None:
        if obj.listing_id is None:
            return None
        return {'id': obj.listing_id, 'url': f'/listings/{obj.listing_id}'}

    def get_allowed_transitions(self, obj) -> list[str]:
        return allowed_transitions(obj.status)


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=LeadStatus.choices)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')

    def validate_note(self, value):
        if _CONTROL_MULTILINE.search(value):
            raise serializers.ValidationError(_CONTROL_MESSAGE)
        return value


class PartnerStatusSerializer(serializers.Serializer):
    partner_status = serializers.ChoiceField(choices=PartnerStatus.choices, allow_blank=True)


class QualificationSerializer(serializers.Serializer):
    """Частичное обновление: переданные ключи записываются (null очищает), остальные не трогаются."""
    q_budget_ok = serializers.BooleanField(allow_null=True, required=False)
    q_term_ok = serializers.BooleanField(allow_null=True, required=False)
    q_knows_repair = serializers.BooleanField(allow_null=True, required=False)
    q_ready_deposit = serializers.BooleanField(allow_null=True, required=False)
