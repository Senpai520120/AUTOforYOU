import json
import uuid
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .dispatcher import get_dispatcher
from .management.commands.run_bot import Command as RunBotCommand
from .middleware import UserBindingMiddleware
from .models import TelegramLinkToken

User = get_user_model()


# ─── TelegramLinkToken model ─────────────────────────────────────────────────

class TelegramLinkTokenModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='token@test.com', password='pass')

    def _make(self, **kw):
        defaults = {'user': self.user, 'expires_at': timezone.now() + timedelta(minutes=30)}
        defaults.update(kw)
        return TelegramLinkToken.objects.create(**defaults)

    def test_valid_token(self):
        self.assertTrue(self._make().is_valid())

    def test_expired_token(self):
        t = self._make(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(t.is_valid())

    def test_used_token(self):
        self.assertFalse(self._make(used=True).is_valid())


# ─── Link-token API ───────────────────────────────────────────────────────────

class TelegramLinkApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='api@test.com', password='pass')
        self.client = APIClient()

    def test_unauth_returns_401(self):
        r = self.client.get('/api/v1/telegram/link-token/')
        self.assertEqual(r.status_code, 401)

    def test_authenticated_returns_token(self):
        self.client.force_authenticate(self.user)
        r = self.client.get('/api/v1/telegram/link-token/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('token', r.data)
        self.assertIn('expires_at', r.data)
        self.assertTrue(TelegramLinkToken.objects.filter(user=self.user).exists())


# ─── Рантайм бота: апдейт → webhook → диспетчер → хендлер ────────────────────
#
# Хендлеры прогоняются по настоящему пути: POST на webhook, Dispatcher aiogram,
# фильтры команд, middleware. Подменён только выход в Telegram API — Bot.__call__,
# через который проходит любой метод (SendMessage и т.д.). Отправленные методы
# складываются в список и проверяются.

BOT_TOKEN = '123456:TEST-TOKEN'
WEBHOOK_SECRET = 'test-secret'
TG_USER_ID = 555001
SITE_URL = 'http://site.test'


def _update(text: str, update_id: int = 1, from_id: int = TG_USER_ID) -> str:
    command_len = len(text.split(' ', 1)[0]) if text.startswith('/') else 0
    message = {
        'message_id': update_id,
        'date': 0,
        'chat': {'id': from_id, 'type': 'private'},
        'from': {'id': from_id, 'is_bot': False, 'first_name': 'Test'},
        'text': text,
    }
    if command_len:
        message['entities'] = [{'type': 'bot_command', 'offset': 0, 'length': command_len}]
    return json.dumps({'update_id': update_id, 'message': message})


class BotRuntimeTestCase(TestCase):
    URL = '/api/v1/telegram/webhook/'

    def setUp(self):
        self.sent = []
        sent = self.sent

        async def fake_call(bot, method, request_timeout=None):
            sent.append(method)

        patcher = patch.object(Bot, '__call__', fake_call)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, text: str, update_id: int = 1, from_id: int = TG_USER_ID):
        with self.settings(
            TELEGRAM_BOT_TOKEN=BOT_TOKEN,
            TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET,
            SITE_URL=SITE_URL,
        ):
            return self.client.post(
                self.URL, data=_update(text, update_id, from_id),
                content_type='application/json',
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=WEBHOOK_SECRET,
            )

    def messages(self) -> list[SendMessage]:
        return [m for m in self.sent if isinstance(m, SendMessage)]

    def replies(self) -> list[str]:
        return [m.text for m in self.messages()]


class BotCommandsTest(BotRuntimeTestCase):
    def test_start_greets_and_lists_commands(self):
        self.assertEqual(self.send('/start').status_code, 200)
        [reply] = self.replies()
        self.assertIn('Ласкаво просимо', reply)
        self.assertIn('/latest', reply)

    def test_help_lists_commands(self):
        self.send('/help')
        [reply] = self.replies()
        self.assertIn('/start', reply)
        self.assertIn('/latest', reply)

    def test_plain_text_is_ignored(self):
        self.assertEqual(self.send('привіт').status_code, 200)
        self.assertEqual(self.replies(), [])

    def test_consecutive_updates_are_all_processed(self):
        """
        Регрессия: вью собирало Dispatcher на каждый запрос и подключало к нему
        один и тот же модульный роутер. Первый апдейт проходил, второй падал
        с RuntimeError 'Router is already attached'.
        """
        self.assertEqual(self.send('/start', update_id=1).status_code, 200)
        self.assertEqual(self.send('/help', update_id=2).status_code, 200)
        self.assertEqual(self.send('/start', update_id=3).status_code, 200)
        self.assertEqual(len(self.replies()), 3)


class BotLatestTest(BotRuntimeTestCase):
    def setUp(self):
        super().setUp()
        self.seller = User.objects.create_user(email='seller@test.com', password='pass')

    def _listing(self, vin: str, **kw):
        from listings.models import Listing
        from vehicles.models import Vehicle
        v = Vehicle.objects.create(
            vin=vin, make='Honda', model='Civic', year=2019,
            engine_cc=1500, fuel_type='petrol', mileage_km=30000,
        )
        defaults = {'vehicle': v, 'seller': self.seller, 'price': '12000.00', 'channel': 'retail'}
        defaults.update(kw)
        return Listing.objects.create(**defaults)

    def _listing_ids(self) -> list[int]:
        return [
            int(m.reply_markup.inline_keyboard[0][0].url.rsplit('/', 1)[1])
            for m in self.messages()
        ]

    def test_no_listings(self):
        self.send('/latest')
        self.assertEqual(self.replies(), ['Наразі немає активних оголошень.'])

    def test_only_retail_in_stock_or_in_transit(self):
        in_stock = self._listing('1HGCM82633A000001', status='in_stock')
        in_transit = self._listing('1HGCM82633A000002', status='in_transit')
        self._listing('1HGCM82633A000003', status='sold')
        self._listing('1HGCM82633A000004', status='in_stock', channel='wholesale')

        self.send('/latest')

        self.assertEqual(sorted(self._listing_ids()), sorted([in_stock.pk, in_transit.pk]))

    def test_button_links_to_listing_page(self):
        listing = self._listing('1HGCM82633A000005')
        self.send('/latest')
        [msg] = self.messages()
        self.assertEqual(msg.reply_markup.inline_keyboard[0][0].url, f'{SITE_URL}/listings/{listing.pk}')
        self.assertIn('Honda Civic 2019', msg.text)

    def test_at_most_five_newest(self):
        from listings.models import Listing
        created = [self._listing(f'1HGCM82633A00010{i}') for i in range(7)]
        # Разводим время создания явно: подряд созданные записи могут получить
        # одинаковый created_at, и порядок между ними не определён.
        base = timezone.now()
        for i, lst in enumerate(created):
            Listing.objects.filter(pk=lst.pk).update(created_at=base + timedelta(minutes=i))
        self.send('/latest')
        self.assertEqual(self._listing_ids(), [lst.pk for lst in reversed(created)][:5])


class BotAccountLinkTest(BotRuntimeTestCase):
    """
    /start link_<uuid> — deep-link из личного кабинета.

    Заменяет прежний TelegramLinkFlowTest: тот не вызывал хендлер вообще,
    а сам присваивал telegram_id и проверял собственное присваивание.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='link@test.com', password='pass')

    def _token(self, **kw):
        defaults = {'user': self.user, 'expires_at': timezone.now() + timedelta(minutes=10)}
        defaults.update(kw)
        return TelegramLinkToken.objects.create(**defaults)

    def test_valid_token_links_account(self):
        token = self._token()
        self.send(f'/start link_{token.token}')

        self.user.refresh_from_db()
        token.refresh_from_db()
        self.assertEqual(self.user.telegram_id, TG_USER_ID)
        self.assertTrue(token.used)
        [reply] = self.replies()
        self.assertIn('успішно', reply)

    def test_token_cannot_be_reused(self):
        token = self._token()
        self.send(f'/start link_{token.token}', update_id=1)
        self.send(f'/start link_{token.token}', update_id=2, from_id=TG_USER_ID + 1)

        self.user.refresh_from_db()
        self.assertEqual(self.user.telegram_id, TG_USER_ID)
        self.assertIn('застаріло', self.replies()[-1])

    def test_expired_token_does_not_link(self):
        token = self._token(expires_at=timezone.now() - timedelta(minutes=1))
        self.send(f'/start link_{token.token}')

        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertIn('застаріло', self.replies()[0])

    def test_used_token_does_not_link(self):
        token = self._token(used=True)
        self.send(f'/start link_{token.token}')

        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertIn('застаріло', self.replies()[0])

    def test_malformed_token(self):
        self.send('/start link_not-a-uuid')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertIn('Невалідне', self.replies()[0])

    def test_unknown_token(self):
        self.send(f'/start link_{uuid.uuid4()}')
        self.assertIn('Невалідне', self.replies()[0])

    def test_other_deeplink_payload_greets(self):
        self.send('/start promo2026')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertIn('Ласкаво просимо', self.replies()[0])


class UserBindingMiddlewareTest(TestCase):
    def _run(self, from_id):
        seen = {}

        async def handler(event, data):
            seen.update(data)

        event = SimpleNamespace(from_user=SimpleNamespace(id=from_id) if from_id else None)
        async_to_sync(UserBindingMiddleware())(handler, event, {})
        return seen

    def test_linked_user_is_resolved(self):
        user = User.objects.create_user(email='mw@test.com', password='pass', telegram_id=777)
        data = self._run(777)
        self.assertTrue(data['is_linked'])
        self.assertEqual(data['telegram_user'], user)

    def test_unknown_telegram_id(self):
        data = self._run(778)
        self.assertFalse(data['is_linked'])
        self.assertIsNone(data['telegram_user'])

    def test_event_without_sender(self):
        data = self._run(None)
        self.assertFalse(data['is_linked'])
        self.assertIsNone(data['telegram_user'])


class RunBotCommandTest(TestCase):
    def test_without_token_exits_with_message(self):
        err = StringIO()
        with self.settings(TELEGRAM_BOT_TOKEN=''), patch('asyncio.run') as run:
            call_command('run_bot', stderr=err)
        run.assert_not_called()
        self.assertIn('TELEGRAM_BOT_TOKEN не задан', err.getvalue())

    def test_polling_uses_shared_dispatcher(self):
        with patch.object(Bot, 'delete_webhook') as delete_webhook, \
                patch.object(Dispatcher, 'start_polling', autospec=True) as start_polling:
            async_to_sync(RunBotCommand._run)(BOT_TOKEN)

        delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
        start_polling.assert_awaited_once()
        self.assertIs(start_polling.await_args.args[0], get_dispatcher())


# ─── send_notification task ───────────────────────────────────────────────────

class SendNotificationTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='notify@test.com', password='pass')

    def test_no_token_returns_no_send(self):
        from integrations.tasks import send_notification
        with self.settings(TELEGRAM_BOT_TOKEN=''):
            result = send_notification(self.user.pk, 'Hello')
        self.assertFalse(result['sent'])
        self.assertEqual(result['reason'], 'no token')

    def test_unlinked_user_skipped(self):
        from integrations.tasks import send_notification
        with self.settings(TELEGRAM_BOT_TOKEN='fake-token'):
            result = send_notification(self.user.pk, 'Hello')
        self.assertFalse(result['sent'])
        self.assertEqual(result['reason'], 'not linked')

    def test_nonexistent_user_handled(self):
        from integrations.tasks import send_notification
        with self.settings(TELEGRAM_BOT_TOKEN='fake-token'):
            result = send_notification(999999, 'Hello')
        self.assertFalse(result['sent'])
        self.assertEqual(result['reason'], 'user not found')

    def test_linked_user_sends(self):
        from integrations.tasks import send_notification
        self.user.telegram_id = 123456789
        self.user.save()

        with self.settings(TELEGRAM_BOT_TOKEN='fake-token'):
            with patch('asyncio.run', return_value=True):
                result = send_notification(self.user.pk, 'Hello')
        self.assertTrue(result['sent'])


# ─── post_listing_to_channel task ────────────────────────────────────────────

class PostListingToChannelTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='seller@test.com', password='pass')

    def test_no_token_skips(self):
        from telegram_bot.tasks import post_listing_to_channel
        with self.settings(TELEGRAM_BOT_TOKEN=''):
            result = post_listing_to_channel(1)
        self.assertFalse(result['posted'])
        self.assertEqual(result['reason'], 'no token')

    def test_listing_not_found(self):
        from telegram_bot.tasks import post_listing_to_channel
        with self.settings(TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHANNEL_ID='@ch'):
            result = post_listing_to_channel(999999)
        self.assertFalse(result['posted'])
        self.assertEqual(result['reason'], 'listing not found')

    def test_no_channel_id_skips(self):
        from listings.models import Listing
        from telegram_bot.tasks import post_listing_to_channel
        from vehicles.models import Vehicle

        v = Vehicle.objects.create(
            vin='1HGBH41JXMN109186', make='Toyota', model='Camry', year=2020,
            engine_cc=2000, fuel_type='petrol', mileage_km=10000,
        )
        listing = Listing.objects.create(
            vehicle=v, seller=self.user, price='15000.00', channel='retail',
        )
        with self.settings(TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHANNEL_ID='', TELEGRAM_B2B_CHANNEL_ID=''):
            result = post_listing_to_channel(listing.pk)
        self.assertFalse(result['posted'])
        self.assertEqual(result['reason'], 'no channel_id')


# ─── Autopost signal ─────────────────────────────────────────────────────────

class ListingAutopostSignalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='signal@test.com', password='pass')

    def _make_vehicle(self):
        from vehicles.models import Vehicle
        return Vehicle.objects.create(
            vin='JT2BF22K1W0066065', make='Honda', model='Civic', year=2019,
            engine_cc=1500, fuel_type='petrol', mileage_km=30000,
        )

    def test_new_retail_listing_schedules_task(self):
        from listings.models import Listing
        v = self._make_vehicle()
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as mock_delay:
            Listing.objects.create(
                vehicle=v, seller=self.user, price='12000.00', channel='retail',
            )
            mock_delay.assert_called_once()

    def test_new_express_buyout_wholesale_schedules_task(self):
        from listings.models import Listing
        v = self._make_vehicle()
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as mock_delay:
            Listing.objects.create(
                vehicle=v, seller=self.user, price='8000.00',
                channel='wholesale', is_express_buyout=True,
            )
            mock_delay.assert_called_once()

    def test_regular_wholesale_does_not_schedule_task(self):
        from listings.models import Listing
        v = self._make_vehicle()
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as mock_delay:
            Listing.objects.create(
                vehicle=v, seller=self.user, price='8000.00', channel='wholesale',
            )
            mock_delay.assert_not_called()

    def test_listing_update_does_not_schedule_task(self):
        from listings.models import Listing
        v = self._make_vehicle()
        listing = Listing.objects.create(
            vehicle=v, seller=self.user, price='12000.00', channel='retail',
        )
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as mock_delay:
            listing.price = '13000.00'
            listing.save()
            mock_delay.assert_not_called()


# ─── Webhook: секрет обязателен ───────────────────────────────────────────────

class TelegramWebhookSecretTest(TestCase):
    """
    Раньше при пустом TELEGRAM_WEBHOOK_SECRET проверка пропускалась целиком:
    кто угодно мог прислать произвольный Update, и он обрабатывался роутером
    бота как настоящее сообщение из Telegram.
    """

    URL = '/api/v1/telegram/webhook/'

    def _post(self, **headers):
        return self.client.post(
            self.URL, data='{}', content_type='application/json', **headers,
        )

    def test_no_token_returns_503(self):
        with self.settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_WEBHOOK_SECRET=''):
            self.assertEqual(self._post().status_code, 503)

    def test_token_without_secret_disables_endpoint(self):
        with self.settings(TELEGRAM_BOT_TOKEN='fake', TELEGRAM_WEBHOOK_SECRET=''):
            resp = self._post()
        self.assertEqual(resp.status_code, 503)

    def test_wrong_secret_rejected(self):
        with self.settings(TELEGRAM_BOT_TOKEN='fake', TELEGRAM_WEBHOOK_SECRET='right'):
            resp = self._post(HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='wrong')
        self.assertEqual(resp.status_code, 403)

    def test_missing_secret_header_rejected(self):
        with self.settings(TELEGRAM_BOT_TOKEN='fake', TELEGRAM_WEBHOOK_SECRET='right'):
            resp = self._post()
        self.assertEqual(resp.status_code, 403)


class TelegramTokenDisabledInTestsTest(SimpleTestCase):
    """
    Страховка от возврата к старому поведению.

    post_save на listings.Listing запускает post_listing_to_channel, а в тестах
    CELERY_TASK_ALWAYS_EAGER=True — задача выполняется синхронно. С реальным
    токеном это были настоящие аутентифицированные запросы в api.telegram.org:
    прогон listings занимал 22.5 с вместо 4.5 с.
    """

    def test_token_is_empty_under_test_runner(self):
        from django.conf import settings
        self.assertEqual(
            settings.TELEGRAM_BOT_TOKEN, '',
            'В тестах TELEGRAM_BOT_TOKEN должен быть пустым — см. core/settings.py',
        )
