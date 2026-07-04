from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from .models import CustomUser, DealerApplication, TrustedShop


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Підтвердження пароля')
    agreed_to_terms = serializers.BooleanField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ('email', 'password', 'password2', 'first_name', 'last_name', 'phone', 'role', 'agreed_to_terms')

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'Паролі не збігаються.'})
        if not attrs.pop('agreed_to_terms'):
            raise serializers.ValidationError(
                {'agreed_to_terms': 'Необхідно погодитися з умовами використання.'}
            )
        return attrs

    def create(self, validated_data):
        user = CustomUser.objects.create_user(**validated_data)
        user.agreed_to_terms_at = timezone.now()
        user.save(update_fields=['agreed_to_terms_at'])
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'email', 'first_name', 'last_name', 'phone', 'role', 'is_verified_dealer', 'created_at')
        read_only_fields = ('id', 'email', 'is_verified_dealer', 'created_at')


class TrustedShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrustedShop
        fields = ('id', 'name', 'type', 'contacts', 'rating', 'notes', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class DealerApplicationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealerApplication
        fields = ('company_name', 'full_name', 'contact_phone', 'documents')


class DealerApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealerApplication
        fields = (
            'id', 'company_name', 'full_name', 'contact_phone', 'documents',
            'status', 'review_notes', 'created_at', 'reviewed_at',
        )
        read_only_fields = fields
