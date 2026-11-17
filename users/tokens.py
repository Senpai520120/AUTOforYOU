"""Токен подтверждения email (задача 1.6). Подход переиспользует 1.7 для сброса пароля.

В подпись входят pk, email и is_email_verified: после подтверждения или смены адреса
старая ссылка перестаёт работать (одноразовость без таблицы в БД).
"""
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = 'users.tokens.EmailVerificationTokenGenerator'

    def _make_hash_value(self, user, timestamp):
        return f'{user.pk}{user.email}{user.is_email_verified}{timestamp}'

    def check_token(self, user, token):
        # Копия базовой проверки, но со своим сроком (базовая читает PASSWORD_RESET_TIMEOUT).
        if not (user and token):
            return False
        try:
            ts_b36, _ = token.split('-')
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token):
                break
        else:
            return False
        ttl = settings.EMAIL_VERIFY_TTL_HOURS * 3600
        return (self._num_seconds(self._now()) - ts) <= ttl


email_verification_token = EmailVerificationTokenGenerator()
