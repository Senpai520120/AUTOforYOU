from django.conf import settings
from rest_framework import serializers
from .models import Region, City, LocalListing, LocalListingImage


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name', 'slug']


class CitySerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = City
        fields = ['id', 'name', 'slug', 'region', 'region_name']


class LocalListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalListingImage
        fields = ['id', 'image', 'source_url', 'is_primary']


class LocalListingListSerializer(serializers.ModelSerializer):
    """Публічний список — без телефону власника."""
    images = LocalListingImageSerializer(many=True, read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = LocalListing
        fields = [
            'id', 'make', 'model', 'year', 'mileage_km', 'engine_cc',
            'fuel_type', 'transmission', 'body_type', 'condition',
            'price', 'currency', 'price_type',
            'region', 'region_name', 'city', 'city_name',
            'description', 'status', 'seller_type',
            'owner_name', 'images', 'created_at', 'updated_at',
        ]
        # contact_phone intentionally excluded from public list

    def get_owner_name(self, obj):
        u = obj.owner
        full = f'{u.first_name} {u.last_name}'.strip()
        return full or u.email.split('@')[0]


class LocalListingDetailSerializer(LocalListingListSerializer):
    """
    Деталь: телефон повертається тільки авторизованим.
    Повна реалізація захисту контактів — C2C-промт 6.
    """

    class Meta(LocalListingListSerializer.Meta):
        fields = LocalListingListSerializer.Meta.fields + ['contact_phone']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        # TODO: C2C-промт 6 — розкривати телефон тільки авторизованим і по явному запиту
        if not (request and request.user and request.user.is_authenticated):
            data['contact_phone'] = None
        return data


class LocalListingCreateSerializer(serializers.ModelSerializer):
    images = LocalListingImageSerializer(many=True, read_only=True)

    class Meta:
        model = LocalListing
        fields = [
            'id', 'make', 'model', 'year', 'mileage_km', 'engine_cc',
            'fuel_type', 'transmission', 'body_type', 'condition',
            'price', 'currency', 'price_type',
            'region', 'city',
            'description', 'status', 'seller_type', 'contact_phone',
            'images', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'images']

    def validate(self, attrs):
        city = attrs.get('city')
        region = attrs.get('region')
        if city and region and city.region_id != region.id:
            raise serializers.ValidationError({'city': 'Місто не належить до вказаної області.'})
        return attrs

    def validate_year(self, value):
        import datetime
        current_year = datetime.date.today().year
        if value < 1900 or value > current_year + 1:
            raise serializers.ValidationError(f'Рік має бути між 1900 та {current_year + 1}.')
        return value

    def create(self, validated_data):
        max_active = getattr(settings, 'LOCAL_LISTING_MAX_ACTIVE', 10)
        owner = self.context['request'].user
        active_count = LocalListing.objects.filter(owner=owner, status=LocalListing.Status.ACTIVE).count()
        if active_count >= max_active:
            raise serializers.ValidationError(
                f'Досягнуто ліміт активних оголошень ({max_active}). '
                f'Закрийте або видаліть існуючі перед подачею нового.'
            )
        # TODO: C2C-промт 2 — після впровадження модерації замінити на status=PENDING
        validated_data['owner'] = owner
        validated_data.setdefault('status', LocalListing.Status.ACTIVE)
        return super().create(validated_data)


class LocalListingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalListing
        fields = [
            'make', 'model', 'year', 'mileage_km', 'engine_cc',
            'fuel_type', 'transmission', 'body_type', 'condition',
            'price', 'currency', 'price_type',
            'region', 'city',
            'description', 'status', 'contact_phone',
        ]

    def validate(self, attrs):
        city = attrs.get('city', getattr(self.instance, 'city', None))
        region = attrs.get('region', getattr(self.instance, 'region', None))
        if city and region and city.region_id != region.id:
            raise serializers.ValidationError({'city': 'Місто не належить до вказаної області.'})
        return attrs

    def validate_status(self, value):
        allowed = {LocalListing.Status.ACTIVE, LocalListing.Status.HIDDEN, LocalListing.Status.SOLD}
        if value not in allowed:
            raise serializers.ValidationError('Можна встановити: active, hidden, sold.')
        return value
