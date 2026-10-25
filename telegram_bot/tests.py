import json
import uuid
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import Update
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
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


class TelegramUnlinkApiTest(TestCase):
    """23-D91: DELETE telegram/link/ - только вошедший, только свою привязку."""
    URL = '/api/v1/telegram/link/'

    def test_anonymous_401(self):
        self.assertEqual(APIClient().delete(self.URL).status_code, 401)

    def test_not_linked_400(self):
        user = User.objects.create_user(email='unlinked@test.com', password='pass')
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.delete(self.URL).status_code, 400)

    def test_linked_200_resets_only_own_telegram_id(self):
        user = User.objects.create_user(email='linked@test.com', password='pass', telegram_id=777001)
        neighbour = User.objects.create_user(email='neighbour@test.com', password='pass', telegram_id=777002)
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.delete(self.URL).status_code, 200)
        user.refresh_from_db()
        neighbour.refresh_from_db()
        self.assertIsNone(user.telegram_id)
        self.assertEqual(neighbour.telegram_id, 777002)


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


class TelegramUpdateTestCase(TestCase):
    """База для тестов, которые разбирают настоящий `Update` или ходят в webhook (23-D4).

    В aiogram Update.event_type - @property поверх @lru_cache: разобранные Update живут в кэше
    класса до конца процесса, и на сборке Python в GitHub Actions это segfault (exit 139)
    после 'OK'. Кэш чистится после каждого теста; страховка проверяет, что он пуст.
    Кэш Django (дедупликация update_id) чистится перед тестом: в locmem он живёт весь прогон.
    """

    def setUp(self):
        super().setUp()
        cache.clear()
        # Cleanup идут в обратном порядке: проверка выполнится после cache_clear.
        self.addCleanup(self._assert_update_cache_empty)
        self.addCleanup(Update.event_type.fget.cache_clear)

    def _assert_update_cache_empty(self):
        self.assertEqual(Update.event_type.fget.cache_info().currsize, 0)


class BotRuntimeTestCase(TelegramUpdateTestCase):
    URL = '/api/v1/telegram/webhook/'

    def setUp(self):
        super().setUp()
        self.sent = []
        sent = self.sent

        async def fake_call(bot, method, request_timeout=None):
            sent.append(method)

        patcher = patch.object(Bot, '__call__', fake_call)
        patcher.start()
        self.addCleanup(patcher.stop)

        # Очистка кэша Update (segfault 139) - в базовом классе TelegramUpdateTestCase,
        # вторая страховка - core.test_runner.IsolatedDiscoverRunner.

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

    def test_latest_hides_lots_when_lots_disabled(self):
        self._listing('1HGCM82633A000201')
        with self.settings(LOTS_ENABLED=False):
            self.send('/latest')
        self.assertEqual(self.replies(), ['Наразі немає активних оголошень.'])

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
        with self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN), patch.object(Bot, 'delete_webhook') as delete_webhook, \
                patch.object(Dispatcher, 'start_polling', autospec=True) as start_polling:
            async_to_sync(RunBotCommand._run)()

        delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
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
        self.assertEqual(result['reason'], 'not_configured')

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

        with self.settings(TELEGRAM_BOT_TOKEN='123456:ABCdef'):
            with patch.object(Bot, 'send_message', new_callable=AsyncMock) as send:
                result = send_notification(self.user.pk, 'Hello')
        # Корутина реально ожидается (раньше asyncio.run был замокан и давал RuntimeWarning).
        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs['chat_id'], 123456789)
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
        self.assertEqual(result['reason'], 'not_configured')

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

class TelegramWebhookSecretTest(TelegramUpdateTestCase):
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


class PostListingToChannelLotsDisabledTest(TestCase):
    def test_queued_task_does_not_publish_when_lots_disabled(self):
        from listings.models import Listing
        from telegram_bot.tasks import post_listing_to_channel
        from tests.factories import make_listing, make_user, make_vehicle
        with patch('telegram_bot.tasks.post_listing_to_channel.delay'):
            listing = make_listing(make_vehicle(), make_user())
        with self.settings(LOTS_ENABLED=False, TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHANNEL_ID='@ch'),                 patch('aiogram.Bot.__call__') as bot_call:
            result = post_listing_to_channel(listing.pk)
        self.assertEqual(result, {'posted': False, 'reason': 'lots disabled'})
        bot_call.assert_not_called()
        self.assertTrue(Listing.objects.filter(pk=listing.pk).exists())


# ─── 5.1: экранирование, привязка, webhook, режимы ───────────────────────────

class BotEscapingTest(BotRuntimeTestCase):
    """07-S3: данные из БД показываются буквально и не ломают отправку."""

    def test_latest_escapes_make_and_does_not_fail(self):
        from tests.factories import make_listing, make_user, make_vehicle
        with patch('telegram_bot.tasks.post_listing_to_channel.delay'):
            make_listing(make_vehicle(make='<b>X & Y', model='"M"'), make_user())
        self.assertEqual(self.send('/latest').status_code, 200)
        [msg] = self.messages()
        self.assertIn('&lt;b&gt;X &amp; Y &quot;M&quot;', msg.text)
        self.assertNotIn('<b>X', msg.text)

    def test_channel_post_escapes_text(self):
        from telegram_bot.provider import SendResult
        from telegram_bot.tasks import post_listing_to_channel
        from tests.factories import make_listing, make_user, make_vehicle
        with patch('telegram_bot.tasks.post_listing_to_channel.delay'):
            listing = make_listing(make_vehicle(make='<i>X & Y'), make_user())
        calls = []
        provider = SimpleNamespace(
            is_configured=lambda: True,
            send_message=lambda chat_id, text, **kw: calls.append(text) or SendResult(ok=True),
            send_photo=lambda *a, **kw: SendResult(ok=False),
        )
        with self.settings(TELEGRAM_CHANNEL_ID='@ch'), \
                patch('telegram_bot.provider.get_telegram_provider', return_value=provider), \
                patch('telegram_bot.tasks.time.sleep'):
            result = post_listing_to_channel(listing.pk)
        self.assertTrue(result['posted'])
        [text] = calls
        self.assertIn('&lt;i&gt;X &amp; Y', text)
        self.assertNotIn('<i>', text)


class BotLinkConflictTest(BotRuntimeTestCase):
    """07-Q1, 07-S4: занятый Telegram и одноразовость токена."""

    def setUp(self):
        super().setUp()
        from tests.factories import make_user
        self.user = make_user()

    def _token(self, **kw):
        defaults = {'user': self.user, 'expires_at': timezone.now() + timedelta(minutes=10)}
        defaults.update(kw)
        return TelegramLinkToken.objects.create(**defaults)

    def test_telegram_taken_by_other_account(self):
        from tests.factories import make_user
        other = make_user(telegram_id=TG_USER_ID)
        token = self._token()
        self.assertEqual(self.send(f'/start link_{token.token}').status_code, 200)

        self.user.refresh_from_db()
        other.refresh_from_db()
        token.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertEqual(other.telegram_id, TG_USER_ID)
        self.assertFalse(token.used)
        [reply] = self.replies()
        self.assertIn('уже прив\'язано до іншого акаунту', reply)

    def test_integrity_error_is_reported_as_taken(self):
        """Гонка: проверка занятости прошла, а уникальный индекс сработал при записи."""
        from django.db import IntegrityError

        from users.models import CustomUser
        token = self._token()

        def failing_save(obj, *a, **kw):
            raise IntegrityError('dup')
        with patch.object(CustomUser, 'save', failing_save):
            self.assertEqual(self.send(f'/start link_{token.token}').status_code, 200)
        token.refresh_from_db()
        self.assertFalse(token.used)
        self.assertIn('іншого акаунту', self.replies()[0])

    def test_same_telegram_same_account_is_already(self):
        self.user.telegram_id = TG_USER_ID
        self.user.save(update_fields=['telegram_id'])
        token = self._token()
        self.assertEqual(self.send(f'/start link_{token.token}').status_code, 200)
        [reply] = self.replies()
        self.assertIn('уже прив\'язано до вашого акаунту', reply)

    def test_second_update_with_same_token_gets_expired(self):
        token = self._token()
        self.send(f'/start link_{token.token}', update_id=1)
        self.send(f'/start link_{token.token}', update_id=2, from_id=TG_USER_ID + 1)
        self.assertIn('успішно', self.replies()[0])
        self.assertIn('застаріло', self.replies()[1])

    def test_token_redeemed_in_parallel_does_not_link(self):
        """Хендлер прочитал токен валидным, но параллельный апдейт успел его погасить: привязки нет."""
        token = self._token()

        def valid_but_redeemed_meanwhile(obj):
            TelegramLinkToken.objects.filter(pk=obj.pk).update(used=True)
            return True
        with patch.object(TelegramLinkToken, 'is_valid', valid_but_redeemed_meanwhile):
            self.send(f'/start link_{token.token}')
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertIn('застаріло', self.replies()[0])


class WebhookReliabilityTest(BotRuntimeTestCase):
    """07-Q6, 23-D100: коды ответа, дедупликация, исключения хендлеров."""

    def _raw(self, body, secret=WEBHOOK_SECRET):
        with self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET):
            return self.client.post(
                self.URL, data=body, content_type='application/json',
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret,
            )

    def test_invalid_json_400(self):
        self.assertEqual(self._raw('{not json').status_code, 400)

    def test_json_without_update_id_400(self):
        self.assertEqual(self._raw('{"message": {}}').status_code, 400)

    def test_non_integer_update_id_400(self):
        self.assertEqual(self._raw('{"update_id": "7"}').status_code, 400)

    def test_json_array_400(self):
        self.assertEqual(self._raw('[1, 2]').status_code, 400)

    def test_handler_exception_returns_200_and_logs_without_pii(self):
        with patch.object(Dispatcher, 'feed_update', side_effect=RuntimeError('boom')), \
                self.assertLogs('telegram_bot.views', level='ERROR') as logs:
            resp = self.send('секретний текст', update_id=42)
        self.assertEqual(resp.status_code, 200)
        out = '\n'.join(logs.output)
        self.assertIn('update_id=42', out)
        self.assertIn('type=message', out)
        self.assertNotIn('секретний текст', out)
        self.assertNotIn(str(TG_USER_ID), out)

    def test_exception_text_with_pii_not_logged(self):
        boom = RuntimeError(f'input_value={TG_USER_ID} text=приватне повідомлення')
        with patch.object(Dispatcher, 'feed_update', side_effect=boom), \
                self.assertLogs('telegram_bot.views', level='ERROR') as logs:
            self.assertEqual(self.send('приватне повідомлення', update_id=43).status_code, 200)
        out = '\n'.join(logs.output)
        self.assertIn('exc=RuntimeError', out)
        self.assertNotIn('приватне', out)
        self.assertNotIn(str(TG_USER_ID), out)
        self.assertNotIn('Traceback', out)

    def test_same_update_id_from_other_bot_is_processed(self):
        self.assertEqual(self.send('/start', update_id=11).status_code, 200)
        with self.settings(TELEGRAM_BOT_TOKEN='777000:OTHER-TEST-TOKEN', TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET):
            resp = self.client.post(
                self.URL, data=_update('/start', 11), content_type='application/json',
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=WEBHOOK_SECRET,
            )
            self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.replies()), 2)

    def test_duplicate_update_processed_once(self):
        self.assertEqual(self.send('/start', update_id=9).status_code, 200)
        self.assertEqual(self.send('/start', update_id=9).status_code, 200)
        self.assertEqual(len(self.replies()), 1)

    def test_failed_update_is_not_retried(self):
        with patch.object(Dispatcher, 'feed_update', side_effect=RuntimeError('boom')) as feed, \
                self.assertLogs('telegram_bot.views', level='ERROR'):
            self.send('/start', update_id=5)
            self.assertEqual(self.send('/start', update_id=5).status_code, 200)
        self.assertEqual(feed.call_count, 1)

    def test_secret_compared_via_compare_digest(self):
        with patch('telegram_bot.views.hmac.compare_digest', return_value=False) as cmp:
            resp = self._raw(_update('/start'))
        self.assertEqual(resp.status_code, 403)
        cmp.assert_called_once()


class RunBotModesTest(TestCase):
    SECRET32 = 'a1B2_c3-' * 4
    URL_OK = 'https://site.test/api/v1/telegram/webhook/'

    def _cfg(self, **kw):
        base = dict(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_UPDATES_MODE='webhook',
                    TELEGRAM_WEBHOOK_SECRET=self.SECRET32, SITE_URL='https://site.test')
        base.update(kw)
        return self.settings(**base)

    def test_webhook_mode_sets_webhook_and_exits(self):
        out = StringIO()
        with self._cfg(), \
                patch.object(Bot, 'set_webhook') as set_webhook, \
                patch.object(Bot, 'get_webhook_info', return_value=SimpleNamespace(url=self.URL_OK)), \
                patch.object(Bot, 'delete_webhook') as delete_webhook, \
                patch.object(Dispatcher, 'start_polling') as start_polling:
            call_command('run_bot', stdout=out)
        set_webhook.assert_awaited_once_with(self.URL_OK, secret_token=self.SECRET32, drop_pending_updates=False)
        delete_webhook.assert_not_called()
        start_polling.assert_not_called()
        self.assertIn(f'Webhook установлен: {self.URL_OK}', out.getvalue())

    def test_webhook_mode_without_secret_fails_and_does_not_touch_webhook(self):
        with self._cfg(TELEGRAM_WEBHOOK_SECRET=''), patch.object(Bot, 'set_webhook') as set_webhook:
            with self.assertRaisesMessage(CommandError, 'TELEGRAM_WEBHOOK_SECRET'):
                call_command('run_bot')
        set_webhook.assert_not_called()

    def test_webhook_mode_with_http_site_url_fails(self):
        with self._cfg(SITE_URL='http://site.test'), patch.object(Bot, 'set_webhook') as set_webhook:
            with self.assertRaisesMessage(CommandError, 'https://'):
                call_command('run_bot')
        set_webhook.assert_not_called()

    def test_webhook_mode_with_short_secret_fails(self):
        with self._cfg(TELEGRAM_WEBHOOK_SECRET='short-secret'), patch.object(Bot, 'set_webhook') as set_webhook:
            with self.assertRaisesMessage(CommandError, '32-256'):
                call_command('run_bot')
        set_webhook.assert_not_called()

    def test_unknown_mode_fails(self):
        with self._cfg(TELEGRAM_UPDATES_MODE='sockets'), patch('asyncio.run') as run:
            with self.assertRaisesMessage(CommandError, 'TELEGRAM_UPDATES_MODE'):
                call_command('run_bot')
        run.assert_not_called()

    def test_polling_mode_runs_polling_not_set_webhook(self):
        with self._cfg(TELEGRAM_UPDATES_MODE='polling'), patch('asyncio.run', side_effect=lambda coro: coro.close()) as run, \
                patch.object(Bot, 'set_webhook') as set_webhook:
            call_command('run_bot', stdout=StringIO())
        run.assert_called_once()
        set_webhook.assert_not_called()
