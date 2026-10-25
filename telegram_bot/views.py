import hmac
import json
import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TelegramLinkToken
from .provider import get_telegram_provider, telegram_real_ready

logger = logging.getLogger(__name__)


class TelegramLinkTokenView(APIView):
    """
    GET /api/v1/telegram/link-token/
    Генерирует deep-link для привязки Telegram-аккаунта в личном кабинете.
    Токен действует 30 минут, одноразовый.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token_obj = TelegramLinkToken.objects.create(
            user=request.user,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', '')
        link = (
            f'https://t.me/{bot_username}?start=link_{token_obj.token}'
            if bot_username else None
        )
        return Response({
            'token': str(token_obj.token),
            'expires_at': token_obj.expires_at.isoformat(),
            'link': link,
            'note': 'Перейдіть за посиланням у Telegram для прив\'язки акаунту. Діє 30 хвилин.',
        })


class TelegramUnlinkView(APIView):
    """
    DELETE /api/v1/telegram/link/
    Відв'язує Telegram-акаунт від профілю поточного користувача.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        if not user.telegram_id:
            return Response({'detail': 'Telegram не прив\'язаний.'}, status=400)
        user.telegram_id = None
        user.save(update_fields=['telegram_id'])
        return Response({'ok': True})


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(View):
    """
    POST /api/v1/telegram/webhook/
    Принимает обновления от Telegram (для прод. webhook-режима).
    Проверяет X-Telegram-Bot-Api-Secret-Token.
    """

    def post(self, request):
        if not telegram_real_ready():
            return HttpResponse('Bot not configured', status=503)

        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
        if not secret:
            # Раньше при пустом секрете проверка пропускалась целиком: кто
            # угодно мог прислать сюда произвольный Update, и он обрабатывался
            # роутером бота как настоящее сообщение из Telegram.
            logger.error(
                'Webhook: TELEGRAM_WEBHOOK_SECRET не задан при заданном токене — '
                'эндпоинт отключён. Задайте секрет и переустановите webhook.'
            )
            return HttpResponse('Webhook secret not configured', status=503)

        incoming = request.META.get('HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN', '')
        if not hmac.compare_digest(incoming.encode('utf-8'), secret.encode('utf-8')):
            logger.warning('Webhook: неверный секрет, отклонено')
            return HttpResponse('Forbidden', status=403)

        try:
            data = json.loads(request.body)
        except ValueError:
            return HttpResponse('Bad request', status=400)
        update_id = data.get('update_id') if isinstance(data, dict) else None
        if isinstance(update_id, bool) or not isinstance(update_id, int):
            return HttpResponse('Bad request', status=400)

        # Тип апдейта для лога: имя поля (message, callback_query...), без содержимого.
        update_type = next((k for k in data if k != 'update_id'), 'unknown')

        # bot_id - часть токена до ':' (сам токен в ключ не кладём): апдейты разных ботов не пересекаются.
        bot_id = str(getattr(settings, 'TELEGRAM_BOT_TOKEN', '')).split(':', 1)[0]
        # Telegram повторяет апдейт, пока не получит 200: повтор с тем же update_id пропускаем.
        try:
            is_new = cache.add(f'tg:update:{bot_id}:{update_id}', 1, timeout=settings.TELEGRAM_UPDATE_DEDUP_TTL)
        except Exception:  # noqa: BLE001 - недоступный кэш не должен ронять webhook
            logger.warning('Webhook: кэш дедупликации недоступен, update_id=%s', update_id)
            is_new = True
        if not is_new:
            logger.info('Webhook: повтор update_id=%s пропущен', update_id)
            return HttpResponse('ok')

        # async_to_sync, а не asyncio.run: так sync_to_async в хендлерах
        # выполняется в потоке запроса и работает с его соединением к БД.
        try:
            async_to_sync(self._process_update)(data)
        except Exception as exc:  # noqa: BLE001 - на подписанный апдейт всегда 200, иначе Telegram шлёт его снова
            # Без traceback и текста исключения: в них бывают текст сообщения и telegram_id
            # (pydantic input_value, ошибки БД). Только update_id, тип апдейта и класс ошибки.
            logger.error('Webhook: ошибка обработки update_id=%s type=%s exc=%s',
                         update_id, update_type, type(exc).__name__)
        return HttpResponse('ok')

    @staticmethod
    async def _process_update(data: dict) -> None:
        from aiogram.types import Update

        from telegram_bot.dispatcher import get_dispatcher

        bot = get_telegram_provider().bot()
        try:
            update = Update.model_validate(data)
            await get_dispatcher().feed_update(bot, update)
        finally:
            await bot.session.close()
