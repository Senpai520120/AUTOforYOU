from rest_framework import serializers

from .models import FaqItem, ImportStep


class ImportStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportStep
        fields = ('title', 'description', 'duration')
        read_only_fields = fields


class FaqItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaqItem
        fields = ('question', 'answer')
        read_only_fields = fields
