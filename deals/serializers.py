from rest_framework import serializers
from .models import Deal, Review


class DealListingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    make = serializers.CharField()
    model = serializers.CharField()
    year = serializers.IntegerField()


class DealUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class ReviewSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source='author.email', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'rating', 'text', 'author_email', 'created_at']


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
