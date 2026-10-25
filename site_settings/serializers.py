from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers

from core.c2c import c2c_enabled, c2c_public_posting_enabled, payments_enabled
from core.modules import module_enabled
from integrations.base import is_placeholder

from .models import SiteSettings


def carvertical_partner_url() -> str:
    """Партнёрская ссылка carVertical из .env. Пусто, плейсхолдер или не https - пустая строка (ссылки нет)."""
    url = str(getattr(settings, 'CARVERTICAL_PARTNER_URL', '') or '').strip()
    if is_placeholder(url):
        return ''
    parsed = urlparse(url)
    return url if parsed.scheme == 'https' and parsed.netloc else ''


class PublicSiteSettingsSerializer(serializers.ModelSerializer):
    """Белый список публичных полей. 6.7 добавит сюда read-only поле (c2c_enabled) не из модели."""

    owner_configured = serializers.BooleanField(read_only=True)
    # Единственный источник текста согласия партнёру: его же leads.services сохраняет в заявку.
    partner_consent_text = serializers.SerializerMethodField()

    # Флаги модулей (задача 2.8): только чтение, источник правды - .env, не модель.
    lots_enabled = serializers.SerializerMethodField()
    b2b_enabled = serializers.SerializerMethodField()
    dealers_enabled = serializers.SerializerMethodField()
    shipments_enabled = serializers.SerializerMethodField()
    vin_reports_enabled = serializers.SerializerMethodField()
    # Задача 6.7: флаги раздела C2C и платежей (из окружения через core.c2c, не из модели).
    c2c_enabled = serializers.SerializerMethodField()
    c2c_public_posting_enabled = serializers.SerializerMethodField()
    payments_enabled = serializers.SerializerMethodField()
    # Задача 3.2a: партнёрская ссылка carVertical из .env; пусто - фронт ссылку не показывает.
    carvertical_partner_url = serializers.SerializerMethodField()

    def get_c2c_enabled(self, obj) -> bool:
        return c2c_enabled()

    def get_c2c_public_posting_enabled(self, obj) -> bool:
        return c2c_public_posting_enabled()

    def get_payments_enabled(self, obj) -> bool:
        return payments_enabled()

    def get_lots_enabled(self, obj) -> bool:
        return module_enabled('lots')

    def get_b2b_enabled(self, obj) -> bool:
        return module_enabled('b2b')

    def get_dealers_enabled(self, obj) -> bool:
        return module_enabled('dealers')

    def get_shipments_enabled(self, obj) -> bool:
        return module_enabled('shipments')

    def get_vin_reports_enabled(self, obj) -> bool:
        return module_enabled('vin_reports')

    def get_carvertical_partner_url(self, obj) -> str:
        return carvertical_partner_url()

    def get_partner_consent_text(self, obj) -> str:
        from leads.services import PARTNER_CONSENT_TEMPLATE
        name = (obj.partner_name or '').strip()
        return PARTNER_CONSENT_TEMPLATE.format(partner=name)[:500] if name else ''

    class Meta:
        model = SiteSettings
        fields = [
            'owner_legal_form', 'owner_legal_name', 'owner_code', 'owner_address',
            'support_email', 'privacy_email', 'phone', 'manager_contact', 'telegram_channel_url',
            'partner_name', 'partner_legal_name',
            'data_retention_years', 'log_retention_days', 'account_deletion_grace_days',
            'legal_docs_approved', 'legal_docs_updated_at',
            'legal_docs_version', 'legal_docs_reconsent_required',
            'owner_configured', 'partner_consent_text',
            'lots_enabled', 'b2b_enabled', 'dealers_enabled', 'shipments_enabled', 'vin_reports_enabled',
            'c2c_enabled', 'c2c_public_posting_enabled', 'payments_enabled',
            'carvertical_partner_url',
        ]
        read_only_fields = [f for f in fields if f != 'partner_consent_text' and not f.endswith('_enabled')]
