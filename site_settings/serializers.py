from rest_framework import serializers

from .models import SiteSettings


class PublicSiteSettingsSerializer(serializers.ModelSerializer):
    """Белый список публичных полей. 6.7 добавит сюда read-only поле (c2c_enabled) не из модели."""

    owner_configured = serializers.BooleanField(read_only=True)

    class Meta:
        model = SiteSettings
        fields = [
            'owner_legal_form', 'owner_legal_name', 'owner_code', 'owner_address',
            'support_email', 'privacy_email', 'phone', 'manager_contact', 'telegram_channel_url',
            'partner_name', 'partner_legal_name',
            'data_retention_years', 'log_retention_days', 'account_deletion_grace_days',
            'legal_docs_approved', 'legal_docs_updated_at',
            'legal_docs_version', 'legal_docs_reconsent_required',
            'owner_configured',
        ]
        read_only_fields = fields
