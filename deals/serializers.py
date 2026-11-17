from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from users.display import public_display_name

from .models import Deal, Review


class DealListingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    make = serializers.CharField()
    model = serializers.CharField()
    year = serializers.IntegerField()


class DealUserSerializer(serializers.Serializer):
    """Контрагент сделки: только id и публичное имя (без email и ФИО целиком)."""
    id = serializers.IntegerField()
    display_name = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField())
    def get_display_name(self, obj):
        return public_display_name(obj)


class ReviewSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id', 'rating', 'text', 'author_name', 'created_at']

    @extend_schema_field(serializers.CharField())
    def get_author_name(self, obj):
        return public_display_name(obj.author)


class DealSerializer(serializers.ModelSerializer):
    listing = DealListingSerializer(read_only=True)
    seller = DealUserSerializer(read_only=True)
    buyer = DealUserSerializer(read_only=True)
    review = ReviewSerializer(read_only=True)

    class Meta:
        model = Deal
        fields = ['id', 'listing', 'seller', 'buyer', 'status', 'created_at', 'confirmed_at', 'review']


class ProposeDealSerializer(serializers.Serializer):
    buyer_id = serializers.IntegerField()


class ReviewCreateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(allow_blank=True, default='')


class SellerRatingSerializer(serializers.Serializer):
    confirmed_deal_count = serializers.IntegerField()
    review_count = serializers.IntegerField()
    avg_rating = serializers.FloatField(allow_null=True)
    has_badge = serializers.BooleanField()
    badge_threshold = serializers.IntegerField()
