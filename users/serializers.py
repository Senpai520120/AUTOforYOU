from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import RegexValidator
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .consents import record_consents
from .models import ConsentDocument, ConsentMethod, CustomUser, DealerApplication, TrustedShop


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Підтвердження пароля')
    agreed_to_terms = serializers.BooleanField(write_only=True)
    # Подтверждение 18+ (Q-шаг 7): без него 400. Версия текста и дата - по механике Н-32.
    confirmed_age_18 = serializers.BooleanField(write_only=True)
    # Роль при регистрации не принимается: поле role в запросе молча игнорируется
    # (DRF отбрасывает неизвестные ключи), пользователь всегда buyer.
    # dealer ставит только approve_application; broker/moderator/admin - админка.

    class Meta:
        model = CustomUser
        fields = ('email', 'password', 'password2', 'first_name', 'last_name', 'phone', 'agreed_to_terms', 'confirmed_age_18')
        # Уникальность email проверяет RegisterView (01-S11: дубль не раскрываем).
        extra_kwargs = {'email': {'validators': []}}

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'Паролі не збігаються.'})
        if not attrs.pop('agreed_to_terms'):
            raise serializers.ValidationError(
                {'agreed_to_terms': 'Необхідно погодитися з умовами використання.'}
            )
        if not attrs.pop('confirmed_age_18'):
            raise serializers.ValidationError(
                {'confirmed_age_18': 'Підтвердіть, що вам виповнилося 18 років.'}
            )
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            user = CustomUser.objects.create_user(**validated_data)
            user.agreed_to_terms_at = timezone.now()
            user.save(update_fields=['agreed_to_terms_at'])
            record_consents(
                user, [ConsentDocument.TERMS, ConsentDocument.PRIVACY, ConsentDocument.AGE_18],
                ConsentMethod.REGISTER,
            )
        return user


UA_PHONE_VALIDATOR = RegexValidator(r'^\+380\d{9}$', 'Телефон у форматі +380XXXXXXXXX.')


class UserProfileSerializer(serializers.ModelSerializer):
    is_admin_role = serializers.BooleanField(read_only=True)
    # Дата окончательного удаления в период отмены (1.8): баннер «Акаунт буде видалено <дата>».
    deletion_scheduled_for = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            'id', 'email', 'first_name', 'last_name', 'phone', 'role',
            'is_verified_dealer', 'is_staff', 'is_admin_role', 'is_email_verified',
            'created_at', 'telegram_id', 'deletion_scheduled_for',
        )
        # Пустой телефон разрешён (DRF не запускает валидаторы на пустой строке), 01-S17.
        extra_kwargs = {'phone': {'validators': [UA_PHONE_VALIDATOR]}}
        # role только для чтения: смена роли — не самообслуживание.
        # Без этого PATCH /auth/profile/ {"role": "admin"} проходил и открывал
        # B2B-доску и чужие переписки по импортным листингам.
        #
        # is_staff отдаётся, чтобы фронт мог показывать админские разделы по
        # тому же признаку, по которому их проверяет бэкенд. Раньше шапка
        # ориентировалась на role, и пользователь с role='admin' видел ссылку
        # на B2B-доску, а в ответ получал 403.
        read_only_fields = (
            'id', 'email', 'role', 'is_verified_dealer', 'is_staff',
            'is_admin_role', 'is_email_verified', 'created_at', 'telegram_id',
        )

    def get_deletion_scheduled_for(self, obj) -> str | None:
        from .services import deletion_due_at
        due = deletion_due_at(obj)
        return due.isoformat() if due else None


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)

    def validate_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Невірний пароль.')
        return value


class TrustedShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrustedShop
        fields = ('id', 'name', 'type', 'contacts', 'rating', 'notes', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class DealerApplicationCreateSerializer(serializers.ModelSerializer):
    # Форма собирает ПІБ, телефон и ссылку на выписку ЄДР. Чекбокс на фронте
    # согласие показывает, но доказать его не может — прямой POST в API
    # проходил мимо. Теперь без согласия заявка не создаётся.
    agreed_to_processing = serializers.BooleanField(write_only=True)
    confirmed_age_18 = serializers.BooleanField(write_only=True)

    class Meta:
        model = DealerApplication
        fields = (
            'company_name', 'full_name', 'contact_phone', 'documents',
            'agreed_to_processing', 'confirmed_age_18',
        )

    def validate(self, attrs):
        # pop, а не просто чтение: apply_for_dealer принимает **validated_data
        # и лишний ключ уронил бы вызов.
        if not attrs.pop('agreed_to_processing'):
            raise serializers.ValidationError(
                {'agreed_to_processing': 'Необхідна згода на обробку персональних даних.'}
            )
        if not attrs.pop('confirmed_age_18'):
            raise serializers.ValidationError(
                {'confirmed_age_18': 'Підтвердіть, що вам виповнилося 18 років.'}
            )
        return attrs


class DealerApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealerApplication
        fields = (
            'id', 'company_name', 'full_name', 'contact_phone', 'documents',
            'status', 'review_notes', 'created_at', 'reviewed_at',
            'agreed_to_processing_at',
        )
        read_only_fields = fields


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """uid и токен проверяются ПЕРВЫМИ: без валидной ссылки подробности про пароль не раскрываем."""
    INVALID_LINK = 'Посилання недійсне або термін його дії минув.'

    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(write_only=True, max_length=128)
    new_password2 = serializers.CharField(write_only=True, max_length=128)

    def validate(self, attrs):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(pk=force_str(urlsafe_base64_decode(attrs['uid'])))
        except (TypeError, ValueError, OverflowError, user_model.DoesNotExist):
            user = None
        if user is None or not user.is_active or not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError({'detail': self.INVALID_LINK})
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password2': 'Паролі не збігаються.'})
        try:
            validate_password(attrs['new_password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)}) from exc
        attrs['user'] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, max_length=128)
    new_password = serializers.CharField(write_only=True, max_length=128)
    new_password2 = serializers.CharField(write_only=True, max_length=128)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs['old_password']):
            raise serializers.ValidationError({'old_password': 'Поточний пароль невірний.'})
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password2': 'Паролі не збігаються.'})
        if attrs['new_password'] == attrs['old_password']:
            raise serializers.ValidationError({'new_password': 'Новий пароль має відрізнятися від поточного.'})
        try:
            validate_password(attrs['new_password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)}) from exc
        return attrs
