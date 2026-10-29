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
from rest_framework.throttling import SimpleRateThrottle

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

LINK_URL = '/api/v1/telegram/link-token/'
BOT_NAME = 'afy_test_bot'


class TelegramLinkApiTest(TestCase):
    """POST link-token: выдача ссылки, честный статус «не налаштовано», аннулирование прежних токенов (5.4)."""

    def setUp(self):
        cache.clear()  # счётчики throttle живут в кэше
        self.user = User.objects.create_user(email='api@test.com', password='pass')
        self.client = APIClient()

    def _configured(self, **kw):
        return self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_USERNAME=BOT_NAME, **kw)

    def test_unauth_returns_401(self):
        self.assertEqual(self.client.post(LINK_URL).status_code, 401)

    def test_get_not_allowed(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(LINK_URL).status_code, 405)

    def test_configured_returns_link_with_bot_username(self):
        self.client.force_authenticate(self.user)
        with self._configured():
            r = self.client.post(LINK_URL)
        self.assertEqual(r.status_code, 200)
        token = TelegramLinkToken.objects.get(user=self.user)
        self.assertEqual(r.data['link'], f'https://t.me/{BOT_NAME}?start=link_{token.token}')
        self.assertEqual(r.data['bot_username'], BOT_NAME)
        self.assertTrue(r.data['configured'])
        self.assertEqual(r.data['expires_at'], token.expires_at.isoformat())
        self.assertIn('30', r.data['note'])

    def test_without_bot_username_not_configured_and_no_token_created(self):
        self.client.force_authenticate(self.user)
        with self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_USERNAME=''):
            r = self.client.post(LINK_URL)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['configured'])
        self.assertIsNone(r.data['link'])
        self.assertFalse(TelegramLinkToken.objects.filter(user=self.user).exists())

    def test_without_bot_token_not_configured(self):
        self.client.force_authenticate(self.user)
        with self.settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_BOT_USERNAME=BOT_NAME):
            r = self.client.post(LINK_URL)
        self.assertFalse(r.data['configured'])
        self.assertFalse(TelegramLinkToken.objects.filter(user=self.user).exists())

    def test_provider_off_not_configured(self):
        self.client.force_authenticate(self.user)
        with self._configured(TELEGRAM_MODE='off'):
            r = self.client.post(LINK_URL)
        self.assertFalse(r.data['configured'])
        self.assertFalse(TelegramLinkToken.objects.filter(user=self.user).exists())

    def test_new_token_revokes_previous_unused_only_for_this_user(self):
        other = User.objects.create_user(email='other-link@test.com', password='pass')
        exp = timezone.now() + timedelta(minutes=10)
        old = TelegramLinkToken.objects.create(user=self.user, expires_at=exp)
        foreign = TelegramLinkToken.objects.create(user=other, expires_at=exp)
        self.client.force_authenticate(self.user)
        with self._configured():
            r = self.client.post(LINK_URL)
        old.refresh_from_db()
        foreign.refresh_from_db()
        self.assertTrue(old.used)
        self.assertFalse(foreign.used)
        self.assertFalse(TelegramLinkToken.objects.get(token=r.data['token']).used)

    def test_throttle_429(self):
        self.client.force_authenticate(self.user)
        with self._configured(), patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'telegram_link': '2/hour'}):
            codes = [self.client.post(LINK_URL).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_throttle_rate_is_configured_in_settings(self):
        from django.conf import settings
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['telegram_link'], '10/hour')


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

    def test_unlink_revokes_unused_tokens(self):
        user = User.objects.create_user(email='tok@test.com', password='pass', telegram_id=777003)
        token = TelegramLinkToken.objects.create(user=user, expires_at=timezone.now() + timedelta(minutes=10))
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.delete(self.URL).status_code, 200)
        token.refresh_from_db()
        self.assertTrue(token.used)


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
                patch.object(Bot, 'set_my_commands') as set_my_commands, \
                patch.object(Dispatcher, 'start_polling', autospec=True) as start_polling:
            async_to_sync(RunBotCommand._run)()

        delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
        start_polling.assert_awaited_once()
        self.assertIs(start_polling.await_args.args[0], get_dispatcher())
        set_my_commands.assert_awaited_once()
        self.assertEqual([c.command for c in set_my_commands.await_args.args[0]],
                         ['start', 'help', 'latest', 'unlink'])


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
                patch.object(Bot, 'set_my_commands') as set_my_commands, \
                patch.object(Dispatcher, 'start_polling') as start_polling:
            call_command('run_bot', stdout=out)
        set_webhook.assert_awaited_once_with(self.URL_OK, secret_token=self.SECRET32, drop_pending_updates=False)
        delete_webhook.assert_not_called()
        start_polling.assert_not_called()
        set_my_commands.assert_awaited_once()
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


# ─── Тексты бота в админке (5.4) ─────────────────────────────────────────────

class BotTextRegistryTest(TestCase):
    def test_data_migration_filled_every_registry_key(self):
        from .models import BotText
        from .texts import REGISTRY
        self.assertEqual(set(BotText.objects.values_list('key', flat=True)), set(REGISTRY))

    def test_defaults_are_valid_for_their_own_rules(self):
        from .texts import REGISTRY, validate_text
        for key, definition in REGISTRY.items():
            with self.subTest(key=key):
                self.assertEqual(validate_text(key, definition.default), [])

    def test_reminder_keys_have_required_placeholders(self):
        from .texts import REGISTRY
        self.assertEqual(REGISTRY['listing_expiring'].placeholders, ('title', 'days', 'renew_url'))
        self.assertIn('renew_url', REGISTRY['listing_expires_today'].placeholders)
        self.assertIn('renew_url', REGISTRY['listing_expired'].placeholders)


class BotTextValidationTest(TestCase):
    def _errors(self, key, text):
        from .texts import validate_text
        return validate_text(key, text)

    def test_unknown_placeholder_rejected(self):
        [err] = self._errors('start', 'Привіт, {name}')
        self.assertIn('{name}', err)

    def test_attribute_access_in_placeholder_rejected(self):
        self.assertEqual(len(self._errors('latest_item', '{title.__class__}')), 1)

    def test_format_spec_rejected(self):
        self.assertEqual(len(self._errors('latest_item', '{title!r}')), 1)

    def test_script_tag_rejected(self):
        errors = self._errors('start', 'Привіт <script>alert(1)</script>')
        self.assertTrue(errors)
        self.assertIn('<script>', errors[0])

    def test_unclosed_tag_rejected(self):
        [err] = self._errors('start', 'Привіт <b>друже')
        self.assertIn('не закрыт тег', err)

    def test_bare_ampersand_and_angle_bracket_rejected(self):
        self.assertEqual(len(self._errors('start', 'Tom & Jerry')), 1)
        self.assertEqual(len(self._errors('start', '2 < 3')), 1)

    def test_escaped_entities_and_allowed_tags_accepted(self):
        self.assertEqual(self._errors('start', '<b>Tom</b> &amp; <i>Jerry</i> <a href="https://x.test">s</a>'), [])

    def test_plain_text_rejects_tags(self):
        self.assertEqual(len(self._errors('btn_view', '<b>Дивитись</b>')), 1)

    def test_model_clean_raises_validation_error(self):
        from django.core.exceptions import ValidationError

        from .models import BotText
        with self.assertRaises(ValidationError) as ctx:
            BotText(key='start', text='<script>').full_clean(exclude=['updated_at'], validate_unique=False)
        self.assertIn('text', ctx.exception.message_dict)


class BotTextRuntimeTest(BotRuntimeTestCase):
    def _set(self, key, text):
        from .models import BotText
        BotText.objects.update_or_create(key=key, defaults={'text': text})

    def test_edit_applies_without_restart(self):
        self.send('/start', update_id=1)  # прогревает кэш
        self._set('start', 'Новий <b>привіт</b>')
        self.send('/start', update_id=2)
        self.assertEqual(self.replies()[-1], 'Новий <b>привіт</b>')

    def test_missing_key_falls_back_to_default_with_warning(self):
        from .models import BotText
        from .texts import REGISTRY
        BotText.objects.filter(key='help').delete()
        with self.assertLogs('telegram_bot.texts', 'WARNING') as logs:
            self.send('/help')
        self.assertEqual(self.replies(), [REGISTRY['help'].default])
        self.assertIn('help', logs.output[0])

    def test_stored_text_with_bad_placeholder_falls_back_to_default(self):
        from .texts import REGISTRY, get_text
        self._set('latest_item', '{zzz}')
        with self.assertLogs('telegram_bot.texts', 'WARNING'):
            text = get_text('latest_item', title='T', price=1, currency='USD', status='S')
        self.assertEqual(text, REGISTRY['latest_item'].default.format(title='T', price=1, currency='USD', status='S'))

    def test_latest_uses_edited_card_template_and_escapes_values(self):
        from tests.factories import make_listing, make_user, make_vehicle
        self._set('latest_item', '<i>{title}</i> / {price}')
        with patch('telegram_bot.tasks.post_listing_to_channel.delay'):
            make_listing(make_vehicle(make='<b>X'), make_user())
        self.send('/latest')
        [text] = self.replies()
        self.assertTrue(text.startswith('<i>&lt;b&gt;X '), text)

    def test_latest_button_text_from_bottext(self):
        from tests.factories import make_listing, make_user, make_vehicle
        self._set('btn_view', 'Дивитись')
        with patch('telegram_bot.tasks.post_listing_to_channel.delay'):
            make_listing(make_vehicle(), make_user())
        self.send('/latest')
        [msg] = self.messages()
        self.assertEqual(msg.reply_markup.inline_keyboard[0][0].text, 'Дивитись')

    def test_empty_latest_text_from_bottext(self):
        self._set('latest_empty', 'Порожньо')
        self.send('/latest')
        self.assertEqual(self.replies(), ['Порожньо'])

    def test_help_sent_with_html_parse_mode(self):
        self.send('/help')
        self.assertEqual(self.messages()[0].parse_mode, 'HTML')


class BotTextAdminTest(TestCase):
    def setUp(self):
        from tests.factories import make_user
        cache.clear()
        self.admin = make_user(is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)

    def _change_url(self, key):
        from django.urls import reverse

        from .models import BotText
        return reverse('admin:telegram_bot_bottext_change', args=[BotText.objects.get(key=key).pk])

    def test_save_with_unknown_placeholder_shows_error_and_does_not_save(self):
        from .models import BotText
        from .texts import REGISTRY
        r = self.client.post(self._change_url('start'), {'text': 'Привіт {unknown}'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '{unknown}')
        self.assertEqual(BotText.objects.get(key='start').text, REGISTRY['start'].default)

    def test_save_with_script_tag_shows_error(self):
        from .models import BotText
        r = self.client.post(self._change_url('start'), {'text': '<script>x</script>'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '&lt;script&gt;')
        self.assertNotEqual(BotText.objects.get(key='start').text, '<script>x</script>')

    def test_valid_save_updates_and_invalidates_cache(self):
        from .texts import get_text
        self.assertIn('Ласкаво', get_text('start'))  # кэш прогрет
        r = self.client.post(self._change_url('start'), {'text': 'Інший <b>текст</b>'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(get_text('start'), 'Інший <b>текст</b>')

    def test_key_is_readonly_on_change_form(self):
        r = self.client.get(self._change_url('start'))
        self.assertNotContains(r, 'name="key"')

    def test_placeholder_hint_lists_allowed(self):
        from .admin import BotTextAdmin
        from .models import BotText
        hint = BotTextAdmin(BotText, None).allowed_placeholders(BotText.objects.get(key='latest_item'))
        self.assertIn('{title}', hint)
        self.assertIn('{status}', hint)


class TelegramLinkTokenAdminTest(TestCase):
    def setUp(self):
        from tests.factories import make_user
        self.admin = make_user(is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)
        self.token = TelegramLinkToken.objects.create(
            user=self.admin, expires_at=timezone.now() + timedelta(minutes=10))

    def test_changelist_masks_token(self):
        from django.urls import reverse
        r = self.client.get(reverse('admin:telegram_bot_telegramlinktoken_changelist'))
        self.assertContains(r, str(self.token.token)[:8] + '…')
        self.assertNotContains(r, str(self.token.token))

    def test_change_form_is_readonly_and_masked(self):
        from django.urls import reverse
        r = self.client.get(reverse('admin:telegram_bot_telegramlinktoken_change', args=[self.token.pk]))
        self.assertNotContains(r, str(self.token.token))
        for field in ('used', 'expires_at_0', 'user', 'token'):
            self.assertNotContains(r, f'name="{field}"')

    def test_add_forbidden(self):
        from django.urls import reverse
        self.assertEqual(self.client.get(reverse('admin:telegram_bot_telegramlinktoken_add')).status_code, 403)


# ─── /unlink, меню команд, ссылка привязки ───────────────────────────────────

class BotUnlinkCommandTest(BotRuntimeTestCase):
    def test_linked_user_unlinked_and_tokens_revoked(self):
        from tests.factories import make_user

        from .texts import REGISTRY
        user = make_user(telegram_id=TG_USER_ID)
        token = TelegramLinkToken.objects.create(user=user, expires_at=timezone.now() + timedelta(minutes=10))
        self.send('/unlink')
        user.refresh_from_db()
        token.refresh_from_db()
        self.assertIsNone(user.telegram_id)
        self.assertTrue(token.used)
        self.assertEqual(self.replies(), [REGISTRY['unlink_ok'].default])

    def test_not_linked_gets_not_linked_reply_and_other_users_untouched(self):
        from tests.factories import make_user

        from .texts import REGISTRY
        other = make_user(telegram_id=TG_USER_ID + 1)
        self.send('/unlink')
        other.refresh_from_db()
        self.assertEqual(other.telegram_id, TG_USER_ID + 1)
        self.assertEqual(self.replies(), [REGISTRY['unlink_not_linked'].default])

    def test_second_link_token_makes_first_stale(self):
        """23-D93: после выдачи нового токена привязка по старому - «посилання застаріло»."""
        from tests.factories import make_user
        cache.clear()
        user = make_user()
        client = APIClient()
        client.force_authenticate(user)
        with self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_USERNAME=BOT_NAME):
            first = client.post(LINK_URL).data['token']
            client.post(LINK_URL)
        self.send(f'/start link_{first}')
        user.refresh_from_db()
        self.assertIsNone(user.telegram_id)
        self.assertIn('застаріло', self.replies()[0])


class SetBotCommandsTest(TestCase):
    def test_command_sets_four_commands(self):
        with self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN), patch.object(Bot, 'set_my_commands') as setter:
            call_command('set_bot_commands', stdout=StringIO())
        [commands] = setter.await_args.args
        self.assertEqual([(c.command, c.description) for c in commands],
                         [('start', 'Привітання'), ('help', 'Список команд'),
                          ('latest', 'Останні оголошення'), ('unlink', "Відв'язати акаунт")])

    def test_descriptions_come_from_bottext(self):
        from .bot_commands import install_bot_commands
        from .models import BotText
        BotText.objects.filter(key='cmd_help').update(text='Допомога')
        cache.clear()
        with patch.object(Bot, 'set_my_commands') as setter:
            async_to_sync(install_bot_commands)(Bot(token=BOT_TOKEN))
        [commands] = setter.await_args.args
        self.assertEqual(commands[1].description, 'Допомога')

    def test_without_token_fails(self):
        with self.settings(TELEGRAM_BOT_TOKEN=''), patch.object(Bot, 'set_my_commands') as setter:
            with self.assertRaisesMessage(CommandError, 'TELEGRAM_BOT_TOKEN'):
                call_command('set_bot_commands')
        setter.assert_not_called()

    def test_run_bot_survives_menu_failure(self):
        from aiogram.exceptions import TelegramNetworkError
        err = TelegramNetworkError(method=SendMessage(chat_id=1, text='x'), message='boom')
        with self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN), patch.object(Bot, 'delete_webhook'), \
                patch.object(Bot, 'set_my_commands', side_effect=err), \
                patch.object(Dispatcher, 'start_polling', autospec=True) as start_polling:
            async_to_sync(RunBotCommand._run)()
        start_polling.assert_awaited_once()


class SetWebhookCommandTest(TestCase):
    SECRET32 = 'a1B2_c3-' * 4

    def _cfg(self, **kw):
        base = dict(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET=self.SECRET32, SITE_URL='https://site.test')
        base.update(kw)
        return self.settings(**base)

    def test_without_secret_fails_and_bot_api_not_called(self):
        with self._cfg(TELEGRAM_WEBHOOK_SECRET=''), patch.object(Bot, 'set_webhook') as set_webhook:
            with self.assertRaisesMessage(CommandError, 'TELEGRAM_WEBHOOK_SECRET'):
                call_command('set_webhook')
        set_webhook.assert_not_called()

    def test_default_url_from_site_url(self):
        out = StringIO()
        url = 'https://site.test/api/v1/telegram/webhook/'
        with self._cfg(), patch.object(Bot, 'set_webhook') as set_webhook, \
                patch.object(Bot, 'get_webhook_info', return_value=SimpleNamespace(url=url)):
            call_command('set_webhook', stdout=out)
        set_webhook.assert_awaited_once_with(url, secret_token=self.SECRET32, drop_pending_updates=False)
        self.assertIn(url, out.getvalue())

    def test_explicit_https_url_overrides_site_url(self):
        url = 'https://other.test/hook/'
        with self._cfg(SITE_URL='http://localhost'), patch.object(Bot, 'set_webhook') as set_webhook, \
                patch.object(Bot, 'get_webhook_info', return_value=SimpleNamespace(url=url)):
            call_command('set_webhook', url, stdout=StringIO())
        set_webhook.assert_awaited_once_with(url, secret_token=self.SECRET32, drop_pending_updates=False)

    def test_http_url_fails(self):
        with self._cfg(), patch.object(Bot, 'set_webhook') as set_webhook:
            with self.assertRaisesMessage(CommandError, 'https://'):
                call_command('set_webhook', 'http://site.test/hook/')
        set_webhook.assert_not_called()

    def test_http_site_url_fails(self):
        with self._cfg(SITE_URL='http://site.test'), patch.object(Bot, 'set_webhook') as set_webhook:
            with self.assertRaisesMessage(CommandError, 'SITE_URL'):
                call_command('set_webhook')
        set_webhook.assert_not_called()

    def test_delete_option_is_gone(self):
        with self._cfg(), self.assertRaises(CommandError):
            call_command('set_webhook', '--delete')


class UnsetWebhookCommandTest(TestCase):
    def _run(self, *args):
        info = SimpleNamespace(url='')
        with self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN), patch.object(Bot, 'get_webhook_info', return_value=info), \
                patch.object(Bot, 'delete_webhook') as delete_webhook:
            call_command('unset_webhook', *args, stdout=StringIO())
        return delete_webhook

    def test_keeps_pending_updates_by_default(self):
        self._run().assert_awaited_once_with(drop_pending_updates=False)

    def test_drop_pending_flag(self):
        self._run('--drop-pending').assert_awaited_once_with(drop_pending_updates=True)


# ─── send_notification: заблокированный бот ──────────────────────────────────

class SendNotificationBlockedTest(TestCase):
    def setUp(self):
        from tests.factories import make_user
        self.user = make_user(telegram_id=424242)
        self.token = TelegramLinkToken.objects.create(
            user=self.user, expires_at=timezone.now() + timedelta(minutes=10))

    def _send(self, exc):
        from integrations.tasks import send_notification
        with self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN), \
                patch.object(Bot, 'send_message', new_callable=AsyncMock, side_effect=exc):
            return send_notification(self.user.pk, 'Hello')

    def test_forbidden_unlinks_and_returns_blocked(self):
        from aiogram.exceptions import TelegramForbiddenError
        result = self._send(TelegramForbiddenError(method=SendMessage(chat_id=1, text='x'),
                                                   message='Forbidden: bot was blocked by the user'))
        self.assertEqual(result, {'sent': False, 'reason': 'blocked'})
        self.user.refresh_from_db()
        self.token.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertTrue(self.token.used)

    def test_bad_request_is_not_retried_and_keeps_binding(self):
        from aiogram.exceptions import TelegramBadRequest
        result = self._send(TelegramBadRequest(method=SendMessage(chat_id=1, text='x'),
                                               message='Bad Request: chat not found'))
        self.assertEqual(result, {'sent': False, 'reason': 'TelegramBadRequest'})
        self.user.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual(self.user.telegram_id, 424242)
        self.assertFalse(self.token.used)


# ─── Посты канала берут тексты из BotText ────────────────────────────────────

class ChannelTextsFromBotTextTest(TestCase):
    def test_express_prefix_button_and_card_from_bottext(self):
        from telegram_bot.provider import SendResult
        from telegram_bot.tasks import post_listing_to_channel
        from tests.factories import make_listing, make_user, make_vehicle

        from .models import BotText
        BotText.objects.filter(key='channel_express_prefix').update(text='<b>СРОЧНО</b>\n')
        BotText.objects.filter(key='btn_view_listing').update(text='Відкрити')
        BotText.objects.filter(key='channel_listing').update(text='{title} за {price} {currency} {url}')
        cache.clear()
        with patch('telegram_bot.tasks.post_listing_to_channel.delay'):
            listing = make_listing(make_vehicle(make='A&B'), make_user(), is_express_buyout=True)
        calls = []
        provider = SimpleNamespace(
            is_configured=lambda: True,
            send_message=lambda chat_id, text, **kw: calls.append((text, kw)) or SendResult(ok=True),
            send_photo=lambda *a, **kw: SendResult(ok=False),
        )
        with self.settings(TELEGRAM_CHANNEL_ID='@ch'), \
                patch('telegram_bot.provider.get_telegram_provider', return_value=provider), \
                patch('telegram_bot.tasks.time.sleep'):
            post_listing_to_channel(listing.pk)
        [(text, kw)] = calls
        self.assertTrue(text.startswith('<b>СРОЧНО</b>\nA&amp;B '), text)
        self.assertEqual(kw['buttons'][0]['text'], 'Відкрити')


# ─── Ревью 5.4: атрибуты, служебные конструкции, сущности, длины ──────────────

class BotTextHardenedValidationTest(TestCase):
    def _errors(self, text, key='start'):
        from .texts import validate_text
        return validate_text(key, text)

    def test_dangerous_or_unsupported_markup_rejected(self):
        bad = {
            'javascript href': '<a href="javascript:alert(1)">x</a>',
            'tg href': '<a href="tg://user?id=1">x</a>',
            'http href': '<a href="http://x.test">x</a>',
            'unquoted tg href': '<a href=tg://x>x</a>',
            'onclick on b': '<b onclick="x">x</b>',
            'placeholder in href': '<a href="{title}">x</a>',
            'href without value': '<a href>x</a>',
            'a without href attr but with id': '<a id="1">x</a>',
            'class on a': '<a href="https://x.test" class="y">x</a>',
            'bad class on code': '<code class="evil">x</code>',
            'style on pre': '<pre style="x">x</pre>',
            'nested a': '<a href="https://x.test">1<a href="https://y.test">2</a></a>',
            'comment': 'a <!-- x --> b',
            'doctype': '<!DOCTYPE x>',
            'pi': '<?pi x>',
            'cdata': '<![CDATA[x]]>',
            'nbsp entity': 'a&nbsp;b',
            'zero charref': 'a&#0;b',
            'surrogate charref': 'a&#xD800;b',
            'huge charref': 'a&#1114112;b',
        }
        for name, text in bad.items():
            with self.subTest(name):
                self.assertTrue(self._errors(text, 'latest_item' if 'title' in text else 'start'), text)

    def test_literal_https_link_and_language_class_accepted(self):
        self.assertEqual(self._errors('<a href="https://x.test/p?a=1">x</a> <code class="language-python">1</code>'), [])

    def test_allowed_entities_accepted(self):
        self.assertEqual(self._errors('&lt; &gt; &amp; &quot; &#169; &#x41;'), [])

    def test_command_description_length(self):
        self.assertEqual(len(self._errors('x' * 257, 'cmd_help')), 1)
        self.assertEqual(len(self._errors('ab', 'cmd_help')), 1)
        self.assertEqual(self._errors('x' * 256, 'cmd_help'), [])

    def test_button_text_length(self):
        self.assertEqual(len(self._errors('x' * 65, 'btn_view')), 1)
        self.assertEqual(self._errors('x' * 64, 'btn_view'), [])


class UnlinkRaceAndUsernameTest(TestCase):
    def test_blocked_old_id_does_not_unlink_new_binding(self):
        from tests.factories import make_user

        from .models import unlink_telegram
        user = make_user(telegram_id=2002)
        token = TelegramLinkToken.objects.create(user=user, expires_at=timezone.now() + timedelta(minutes=10))
        self.assertFalse(unlink_telegram(user.pk, only_telegram_id=1001))  # старый id, привязка уже новая
        user.refresh_from_db()
        token.refresh_from_db()
        self.assertEqual(user.telegram_id, 2002)
        self.assertFalse(token.used)

    def test_blocked_current_id_unlinks(self):
        from tests.factories import make_user

        from .models import unlink_telegram
        user = make_user(telegram_id=1001)
        self.assertTrue(unlink_telegram(user.pk, only_telegram_id=1001))
        user.refresh_from_db()
        self.assertIsNone(user.telegram_id)

    def test_invalid_bot_username_means_not_configured(self):
        from tests.factories import make_user
        cache.clear()
        user = make_user()
        client = APIClient()
        client.force_authenticate(user)
        for name in ('ab', 'bad name', 'x' * 33, 'bot/../x'):
            with self.subTest(name), self.settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_USERNAME=name):
                self.assertFalse(client.post(LINK_URL).data['configured'])
        self.assertFalse(TelegramLinkToken.objects.filter(user=user).exists())


class MigrationDefaultsFrozenTest(SimpleTestCase):
    def test_migration_does_not_import_live_registry(self):
        import importlib
        import inspect
        mod = importlib.import_module('telegram_bot.migrations.0003_bottext_defaults')
        self.assertNotIn('REGISTRY', inspect.getsource(mod))
        self.assertIn('start', mod.DEFAULTS)
