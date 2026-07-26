from rest_framework import serializers

from .models import SavedSearch


class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ['id', 'name', 'filters', 'notify', 'last_notified_at', 'created_at']
        read_only_fields = ['last_notified_at', 'created_at']
