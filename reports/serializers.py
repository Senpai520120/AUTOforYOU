from rest_framework import serializers

from .models import Report


class ReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'listing', 'reported_user', 'reason', 'comment']

    def validate(self, attrs):
        listing = attrs.get('listing')
        reported_user = attrs.get('reported_user')
        if not listing and not reported_user:
            raise serializers.ValidationError('Вкажіть listing або reported_user.')
        if listing and reported_user:
            raise serializers.ValidationError('Вкажіть тільки одне: або listing, або reported_user.')

        reporter = self.context['request'].user

        # Duplicate active report check
        if listing:
            if Report.objects.filter(reporter=reporter, listing=listing, status=Report.Status.NEW).exists():
                raise serializers.ValidationError('Ви вже подали скаргу на це оголошення.')
        if reported_user:
            if reported_user == reporter:
                raise serializers.ValidationError('Не можна поскаржитися на себе.')
            if Report.objects.filter(reporter=reporter, reported_user=reported_user, status=Report.Status.NEW).exists():
                raise serializers.ValidationError('Ви вже подали скаргу на цього користувача.')
        return attrs

    def create(self, validated_data):
        validated_data['reporter'] = self.context['request'].user
        return super().create(validated_data)


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'listing', 'reported_user', 'reason', 'comment', 'status', 'created_at']
