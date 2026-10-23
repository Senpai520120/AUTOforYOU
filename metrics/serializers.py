from collections.abc import Mapping

from rest_framework import serializers

from .models import MetricKey

PUBLIC_KEYS = (MetricKey.CALCULATOR_VISIT, MetricKey.MOBILE_BAR_CLICK)


class MetricEventSerializer(serializers.Serializer):
    """Whitelist: только два клиентских ключа, лишние поля отклоняются."""
    key = serializers.ChoiceField(choices=[k.value for k in PUBLIC_KEYS])

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            extra = set(data) - set(self.fields)
            if extra:
                raise serializers.ValidationError({'non_field_errors': ['Зайві поля не дозволені.']})
        return super().to_internal_value(data)
