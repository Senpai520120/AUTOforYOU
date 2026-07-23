import datetime

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Region, City, LocalListing, LocalListingImage, PromotionTariff
from .services import SUBSTANTIVE_FIELDS


class PromotionTariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromotionTariff
        fields = ['id', 'code', 'name', 'type', 'price', 'currency', 'duration_days', 'description']


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
    """Публічний список — тільки active, без телефону та причини відхилення."""
    images = LocalListingImageSerializer(many=True, read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    owner_name = serializers.SerializerMethodField()
    seller_has_badge = serializers.SerializerMethodField()

    class Meta:
        model = LocalListing
        fields = [
            'id', 'make', 'model', 'year', 'mileage_km', 'engine_cc',
            'fuel_type', 'transmission', 'body_type', 'condition',
            'price', 'currency', 'price_type',
            'region', 'region_name', 'city', 'city_name',
            'description', 'status', 'seller_type',
            'owner_name', 'images',
            'expires_at', 'promoted_until', 'bumped_at',
            'created_at', 'updated_at',
            'seller_has_badge',
        ]
        # contact_phone intentionally excluded from public list

    @extend_schema_field(serializers.CharField())
    def get_owner_name(self, obj):
        u = obj.owner
        full = f'{u.first_name} {u.last_name}'.strip()
        return full or u.email.split('@')[0]

    @extend_schema_field(serializers.BooleanField())
    def get_seller_has_badge(self, obj):
        from django.conf import settings
        threshold = getattr(settings, 'SELLER_BADGE_THRESHOLD', 3)
        from deals.models import Deal
        count = Deal.objects.filter(seller=obj.owner, status='confirmed').count()
        return count >= threshold


class LocalListingDetailSerializer(LocalListingListSerializer):
    """
    Деталь: телефон і причина відхилення повертаються авторизованим/власнику.
    Повна реалізація захисту контактів — C2C-промт 6.
    """
    seller_avg_rating = serializers.SerializerMethodField()
    seller_deal_count = serializers.SerializerMethodField()

    class Meta(LocalListingListSerializer.Meta):
        fields = LocalListingListSerializer.Meta.fields + [
            'contact_phone', 'rejection_reason',
            'seller_avg_rating', 'seller_deal_count',
        ]

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_seller_avg_rating(self, obj):
        from django.db.models import Avg
        from deals.models import Review
        agg = Review.objects.filter(target=obj.owner).aggregate(avg=Avg('rating'))
        return round(agg['avg'], 1) if agg['avg'] else None

    @extend_schema_field(serializers.IntegerField())
    def get_seller_deal_count(self, obj):
        from deals.models import Deal
        return Deal.objects.filter(seller=obj.owner, status='confirmed').count()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        is_auth = request and request.user and request.user.is_authenticated
        is_owner = is_auth and request.user == instance.owner
        is_staff = is_auth and request.user.is_staff

        # Phone is always None in detail — use /contact/ endpoint instead
        data['contact_phone'] = None

        # Причину відхилення бачить тільки власник або адмін
        if not (is_owner or is_staff):
            data['rejection_reason'] = None

        return data


class LocalListingOwnerSerializer(LocalListingDetailSerializer):
    """Серіалізатор для кабінету власника — бачить всі статуси та причину відхилення."""
    class Meta(LocalListingDetailSerializer.Meta):
        fields = LocalListingDetailSerializer.Meta.fields + ['expiry_warned']


class LocalListingCreateSerializer(serializers.ModelSerializer):
    images = LocalListingImageSerializer(many=True, read_only=True)
    agreed_to_rules = serializers.BooleanField(write_only=True)

    class Meta:
        model = LocalListing
        fields = [
            'id', 'make', 'model', 'year', 'mileage_km', 'engine_cc',
            'fuel_type', 'transmission', 'body_type', 'condition',
            'price', 'currency', 'price_type',
            'region', 'city',
            'description', 'status', 'seller_type', 'contact_phone',
            'images', 'created_at', 'updated_at',
            'agreed_to_rules',
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at', 'images']

    def validate_agreed_to_rules(self, value):
        if not value:
            raise serializers.ValidationError(
                'Необхідно погодитися з правилами розміщення оголошень.'
            )
        return value

    def validate(self, attrs):
        city = attrs.get('city')
        region = attrs.get('region')
        if city and region and city.region_id != region.id:
            raise serializers.ValidationError({'city': 'Місто не належить до вказаної області.'})
        return attrs

    def validate_year(self, value):
        current_year = datetime.date.today().year
        if value < 1900 or value > current_year + 1:
            raise serializers.ValidationError(f'Рік має бути між 1900 та {current_year + 1}.')
        return value

    def create(self, validated_data):
        from .antispam import detect_contacts
        from django.conf import settings as dj_settings

        agreed = validated_data.pop('agreed_to_rules')
        max_active = getattr(settings, 'LOCAL_LISTING_MAX_ACTIVE', 10)
        owner = self.context['request'].user

        # Рахуємо active + pending (щоб уникнути обходу ліміту через spam pending)
        active_count = LocalListing.objects.filter(
            owner=owner,
            status__in=[LocalListing.Status.ACTIVE, LocalListing.Status.PENDING],
        ).count()
        if active_count >= max_active:
            raise serializers.ValidationError(
                f'Досягнуто ліміт активних оголошень ({max_active}). '
                f'Закрийте або видаліть існуючі перед подачею нового.'
            )

        validated_data['owner'] = owner
        validated_data['status'] = LocalListing.Status.PENDING
        if agreed:
            validated_data['agreed_to_rules'] = True
            validated_data['agreed_to_rules_at'] = timezone.now()

        antispam_mode = getattr(dj_settings, 'ANTISPAM_MODE', 'soft')
        description = validated_data.get('description', '')
        detected = detect_contacts(description) if antispam_mode != 'off' else []
        if detected:
            if antispam_mode == 'hard':
                raise serializers.ValidationError({
                    'description': 'Текст містить контактні дані (телефон, посилання або месенджер). Видаліть їх.'
                })
            validated_data['has_contact_in_text'] = True

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
        # Власник може тільки знімати/продавати — не модерувати
        allowed_owner = {LocalListing.Status.HIDDEN, LocalListing.Status.SOLD}
        if value not in allowed_owner:
            raise serializers.ValidationError('Можна встановити: hidden, sold.')
        return value

    def update(self, instance, validated_data):
        from .antispam import detect_contacts
        from django.conf import settings as dj_settings

        current_status = instance.status
        substantive_changed = bool(SUBSTANTIVE_FIELDS & set(validated_data.keys()))

        # Суттєва правка active → ремодерація
        if substantive_changed and current_status == LocalListing.Status.ACTIVE:
            validated_data['status'] = LocalListing.Status.PENDING
            validated_data['rejection_reason'] = ''

        # Будь-яка правка rejected → ремодерація (власник виправив)
        elif current_status == LocalListing.Status.REJECTED:
            validated_data['status'] = LocalListing.Status.PENDING
            validated_data['rejection_reason'] = ''

        antispam_mode = getattr(dj_settings, 'ANTISPAM_MODE', 'soft')
        if antispam_mode != 'off' and 'description' in validated_data:
            detected = detect_contacts(validated_data['description'])
            if detected:
                if antispam_mode == 'hard':
                    raise serializers.ValidationError({
                        'description': 'Текст містить контактні дані. Видаліть їх.'
                    })
                validated_data['has_contact_in_text'] = True
            else:
                validated_data['has_contact_in_text'] = False

        return super().update(instance, validated_data)
