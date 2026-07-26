from rest_framework import serializers

from .models import Favorite


class FavoriteSerializer(serializers.ModelSerializer):
    listing_type = serializers.SerializerMethodField()
    listing_id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Favorite
        fields = ['id', 'listing_type', 'listing_id', 'title', 'url', 'price', 'currency', 'image_url', 'created_at']

    def get_listing_type(self, obj):
        return 'local' if obj.local_listing_id else 'imported'

    def get_listing_id(self, obj):
        return obj.local_listing_id or obj.imported_listing_id

    def get_title(self, obj):
        if obj.local_listing:
            ll = obj.local_listing
            return f'{ll.make} {ll.model} {ll.year}'
        if obj.imported_listing:
            v = obj.imported_listing.vehicle
            return f'{v.make} {v.model} {v.year}'
        return ''

    def get_url(self, obj):
        if obj.local_listing_id:
            return f'/local/{obj.local_listing_id}'
        if obj.imported_listing_id:
            return f'/listings/{obj.imported_listing_id}'
        return '/'

    def get_price(self, obj):
        if obj.local_listing:
            return obj.local_listing.price
        if obj.imported_listing:
            return obj.imported_listing.price
        return None

    def get_currency(self, obj):
        if obj.local_listing:
            return obj.local_listing.currency
        if obj.imported_listing:
            return obj.imported_listing.currency
        return None

    def get_image_url(self, obj):
        try:
            if obj.local_listing:
                imgs = obj.local_listing.images.all()
                primary = next((i for i in imgs if i.is_primary), None) or (imgs[0] if imgs else None)
                return primary.image or primary.source_url if primary else None
            if obj.imported_listing:
                imgs = obj.imported_listing.vehicle.images.all()
                primary = next((i for i in imgs if i.is_primary), None) or (imgs[0] if imgs else None)
                return primary.image or primary.source_url if primary else None
        except Exception:
            return None
        return None
