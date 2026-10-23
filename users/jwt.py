"""JWT с версией сессий (задача 1.7).

Claim `sv` = CustomUser.session_version на момент выдачи. Несовпадение с текущей версией
пользователя - токен отозван (смена пароля, logout-all, бан). Токены без `sv` - версия 0.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework_simplejwt import serializers as jwt_serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

SESSION_CLAIM = 'sv'


def token_session_version(token):
    try:
        return int(token.get(SESSION_CLAIM, 0))
    except (TypeError, ValueError):
        return -1


class VersionedRefreshToken(RefreshToken):
    """Единая точка выдачи: access наследует claim `sv` от refresh."""

    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token[SESSION_CLAIM] = user.session_version
        return token


class TokenObtainPairSerializer(jwt_serializers.TokenObtainPairSerializer):
    token_class = VersionedRefreshToken


class TokenRefreshSerializer(jwt_serializers.TokenRefreshSerializer):
    """Refresh старой версии отклоняется ДО выдачи нового токена.

    Проверка и ротация идут под блокировкой строки пользователя; revoke_all_sessions берёт ту же
    блокировку, поэтому параллельная ротация не оставит живого refresh после отзыва.
    """
    token_class = VersionedRefreshToken

    def validate(self, attrs):
        with transaction.atomic():
            refresh = self.token_class(attrs['refresh'])  # подпись, срок, blacklist
            user = (
                get_user_model().objects.select_for_update()
                .filter(pk=refresh.get(api_settings.USER_ID_CLAIM)).first()
            )
            if user is None or token_session_version(refresh) != user.session_version:
                raise TokenError('Token session revoked')
            return super().validate(attrs)
