from rest_framework import serializers


class LotImportRequestSerializer(serializers.Serializer):
    """
    Тело POST /api/v1/lots/import/.

    source='manual' (default) → lot_data обязателен.
    source='apify'            → lot_url обязателен.
    """
    source = serializers.ChoiceField(choices=['manual', 'apify'], default='manual')
    lot_data = serializers.DictField(required=False, help_text='JSON лота для ручного импорта')
    lot_url = serializers.URLField(required=False, help_text='URL лота на Copart/IAAI для Apify-импорта')

    def validate(self, attrs):
        source = attrs.get('source', 'manual')
        if source == 'manual' and not attrs.get('lot_data'):
            raise serializers.ValidationError({'lot_data': 'Обязателен при source=manual'})
        if source == 'apify' and not attrs.get('lot_url'):
            raise serializers.ValidationError({'lot_url': 'Обязателен при source=apify'})
        return attrs
