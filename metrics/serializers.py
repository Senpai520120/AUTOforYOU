from rest_framework import serializers

from .models import MetricKey

# С фронта принимаются только события без серверной точки (8.7); остальные ключи пишет сервер.
PUBLIC_KEYS = (MetricKey.CALCULATOR_VISIT, MetricKey.MOBILE_BAR_CLICK)


class MetricEventSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=[(k.value, k.label) for k in PUBLIC_KEYS])

    def validate(self, attrs):
        extra = set(self.initial_data) - {'key'} if isinstance(self.initial_data, dict) else set()
        if extra:
            raise serializers.ValidationError('Зайві поля не приймаються.')
        return attrs
