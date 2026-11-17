from django.conf import settings
from django.http import Http404
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from core.c2c import c2c_public_posting_enabled
from local_listings.models import LocalListing

from .models import Report

LISTING_NOT_FOUND = 'Оголошення не знайдено.'


class ReportCreateSerializer(serializers.ModelSerializer):
    """Жалоба на объявление (4.13, B8/B9).

    B9: принимается только ACTIVE-объявление; несуществующее и недоступное (pending, hidden, rejected, ...)
    дают один и тот же 404 «Оголошення не знайдено.» - по ответу не узнать, есть ли скрытое объявление.
    ``reported_user`` от клиента не принимается: нарушитель - владелец объявления (админка берёт его из
    ``listing.owner``), жалоба на произвольного пользователя без объявления невозможна.
    """
    listing = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    comment = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = Report
        fields = ['id', 'listing', 'reason', 'comment']

    def validate_comment(self, value):
        limit = settings.REPORT_COMMENT_MAX_LENGTH
        if len(value) > limit:
            raise serializers.ValidationError(f'Коментар не довше {limit} символів.')
        return value

    def validate_listing(self, value):
        # 6.7: жалоба на C2C-объявление закрыта при выключенном разделе и в засеве (404, как у middleware).
        if not c2c_public_posting_enabled():
            raise Http404
        listing = LocalListing.objects.filter(pk=value, status=LocalListing.Status.ACTIVE).first()
        if listing is None:
            raise NotFound(LISTING_NOT_FOUND)
        return listing

    def validate(self, attrs):
        reporter = self.context['request'].user
        listing = attrs['listing']
        if listing.owner_id == reporter.pk:
            raise serializers.ValidationError('Не можна поскаржитися на власне оголошення.')
        if Report.objects.filter(reporter=reporter, listing=listing, status=Report.Status.NEW).exists():
            raise serializers.ValidationError('Ви вже подали скаргу на це оголошення.')
        return attrs

    def create(self, validated_data):
        validated_data['reporter'] = self.context['request'].user
        return super().create(validated_data)

    def to_representation(self, instance):
        return {
            'id': instance.pk, 'listing': instance.listing_id,
            'reason': instance.reason, 'comment': instance.comment,
        }


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['id', 'listing', 'reported_user', 'reason', 'comment', 'status', 'created_at']
