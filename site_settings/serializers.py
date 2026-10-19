from rest_framework import serializers

from .models import SiteSettings


class PublicSiteSettingsSerializer(serializers.ModelSerializer):
    """Белый список публичных полей. 6.7 добавит сюда read-only поле (c2c_enabled) не из модели."""

    owner_configured = serializers.BooleanField(read_only=True)
    # Единственный источник текста согласия партнёру: его же leads.services сохраняет в заявку.
    partner_consent_text = serializers.SerializerMethodField()

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
        ]
        read_only_fields = [f for f in fields if f != 'partner_consent_text']
