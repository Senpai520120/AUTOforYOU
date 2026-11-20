from rest_framework import serializers

from local_listings.filters import clean_filter_params

from .models import SavedSearch


class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ['id', 'name', 'filters', 'notify', 'last_notified_at', 'created_at']
        read_only_fields = ['last_notified_at', 'created_at']

    def validate_name(self, value):
        if '\x00' in value:
            raise serializers.ValidationError('Недопустимі символи.')
        return value

    def validate_filters(self, value):
        # 10.22: білий список ключів і типів як у публічному фільтрі каталогу.
        return clean_filter_params(value)
