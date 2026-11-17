"""Задача 4.10 (часть 1): подтверждение телефона собственным контактом Telegram. Сеть не используется."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tests.factories import auth_client, make_user
from users.models import CustomUser

from .phone_verify import (
    NOT_LINKED,
    NOT_OWN,
    OK,
    TAKEN,
    NotConfigured,
    SmsVerifier,
    TelegramContactVerifier,
    mask_phone,
    normalize_e164,
)

TG = 777000111


def contact_message(from_id, contact_user_id, phone='380671234567'):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=from_id),
        contact=SimpleNamespace(user_id=contact_user_id, phone_number=phone),
        answer=AsyncMock(),
    )


class TestNormalize(TestCase):
    def test_e164(self):
        self.assertEqual(normalize_e164('380671234567'), '+380671234567')
        self.assertEqual(normalize_e164('+38 (067) 123-45-67'), '+380671234567')
        self.assertEqual(normalize_e164('12'), '')

    def test_mask(self):
        self.assertEqual(mask_phone('+380671234567'), '+380*******67')


class TestContactVerifier(TestCase):
    def setUp(self):
        self.user = make_user(telegram_id=TG)

    def confirm(self, **kw):
        params = {'telegram_id': TG, 'contact_user_id': TG, 'phone_number': '380671234567', **kw}
        return TelegramContactVerifier().confirm(**params)

    def test_own_contact_verifies(self):
        self.assertEqual(self.confirm(), OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.verified_phone, '+380671234567')
        self.assertIsNotNone(self.user.phone_verified_at)

    def test_foreign_contact_rejected(self):
        self.assertEqual(self.confirm(contact_user_id=TG + 1), NOT_OWN)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)
        self.assertIsNone(self.user.verified_phone)

    def test_contact_without_user_id_rejected(self):
        self.assertEqual(self.confirm(contact_user_id=None), NOT_OWN)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_unlinked_chat_rejected(self):
        self.assertEqual(self.confirm(telegram_id=TG + 5, contact_user_id=TG + 5), NOT_LINKED)
        self.assertFalse(CustomUser.objects.exclude(verified_phone=None).exists())

    def test_phone_taken_by_other_account(self):
        make_user(verified_phone='+380671234567')
        self.assertEqual(self.confirm(), TAKEN)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_inactive_user_not_verified(self):
        CustomUser.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.confirm(), NOT_LINKED)

    def test_deleted_user_not_verified(self):
        from django.utils import timezone
        CustomUser.objects.filter(pk=self.user.pk).update(deleted_at=timezone.now())  # is_active остаётся True
        self.assertEqual(self.confirm(), NOT_LINKED)

    def test_unique_race_returns_taken(self):
        from unittest.mock import patch

        from django.db import IntegrityError
        with patch.object(CustomUser, 'save', side_effect=IntegrityError):
            self.assertEqual(self.confirm(), TAKEN)


class TestContactHandler(TestCase):
    def test_handler_verifies_and_answers_without_phone_in_log(self):
        from .handlers import on_contact
        user = make_user(telegram_id=TG)
        message = contact_message(TG, TG)
        with self.assertLogs('telegram_bot.handlers', level='INFO') as logs:
            async_to_sync(on_contact)(message)
        user.refresh_from_db()
        self.assertEqual(user.verified_phone, '+380671234567')
        self.assertIn('Телефон підтверджено', message.answer.call_args.args[0])
        self.assertNotIn('671234567', '\n'.join(logs.output))

    def test_handler_rejects_forwarded_contact(self):
        from .handlers import on_contact
        user = make_user(telegram_id=TG)
        message = contact_message(TG, 123)
        async_to_sync(on_contact)(message)
        user.refresh_from_db()
        self.assertIsNone(user.phone_verified_at)
        self.assertIn('власний контакт', message.answer.call_args.args[0])

    def test_link_ok_asks_for_contact(self):
        from datetime import timedelta

        from django.utils import timezone

        from .handlers import _handle_link_token
        from .models import TelegramLinkToken
        user = make_user()
        token = TelegramLinkToken.objects.create(user=user, expires_at=timezone.now() + timedelta(minutes=5))
        message = SimpleNamespace(from_user=SimpleNamespace(id=TG), answer=AsyncMock())
        async_to_sync(_handle_link_token)(message, str(token.token))
        self.assertEqual(message.answer.await_count, 2)
        markup = message.answer.call_args.kwargs['reply_markup']
        self.assertTrue(markup.keyboard[0][0].request_contact)


class TestSms(TestCase):
    @override_settings(SMS_VERIFY_ENABLED=False)
    def test_sms_not_configured(self):
        with self.assertRaises(NotConfigured):
            SmsVerifier().start(None)
        with self.assertRaises(NotConfigured):
            SmsVerifier().confirm()


class TestProfileAndPrivacy(TestCase):
    def test_profile_exposes_flag_read_only(self):
        user = make_user()
        client = auth_client(user)
        data = client.get('/api/v1/auth/profile/').json()
        self.assertFalse(data['phone_verified'])
        resp = client.patch('/api/v1/auth/profile/', {'verified_phone': '+380500000000'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['verified_phone'])
        user.refresh_from_db()
        self.assertIsNone(user.verified_phone)

    def test_anonymize_clears_verified_phone(self):
        from users.services import anonymize_user
        user = make_user(verified_phone='+380671234567')
        CustomUser.objects.filter(pk=user.pk).update(phone_verified_at='2026-11-01T00:00:00Z')
        anonymize_user(user)
        user.refresh_from_db()
        self.assertIsNone(user.verified_phone)
        self.assertIsNone(user.phone_verified_at)

    def test_admin_reset_phone_verification(self):
        from django.test import Client
        from django.utils import timezone

        from tests.factories import make_staff
        user = make_user(verified_phone='+380671234567')
        CustomUser.objects.filter(pk=user.pk).update(phone_verified_at=timezone.now())
        client = Client()
        client.force_login(make_staff(superuser=True))
        resp = client.post('/admin/users/customuser/', {
            'action': 'reset_phone_verification', '_selected_action': [user.pk],
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertIsNone(user.verified_phone)
        self.assertIsNone(user.phone_verified_at)

    def test_anonymous_profile_401(self):
        self.assertEqual(APIClient().get('/api/v1/auth/profile/').status_code, 401)
