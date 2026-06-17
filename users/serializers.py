from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import CustomUser, TrustedShop


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Подтверждение пароля')

    class Meta:
        model = CustomUser
        fields = ('email', 'password', 'password2', 'first_name', 'last_name', 'phone', 'role')

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'Пароли не совпадают.'})
        return attrs

    def create(self, validated_data):
        return CustomUser.objects.create_user(**validated_data)


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
