import asyncio
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TelegramLinkToken

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


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(View):
    """
    POST /api/v1/telegram/webhook/
    Принимает обновления от Telegram (для прод. webhook-режима).
    Проверяет X-Telegram-Bot-Api-Secret-Token.
    """

    def post(self, request):
        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
        if secret:
            incoming = request.META.get('HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN', '')
            if incoming != secret:
                logger.warning('Webhook: неверный секрет, отклонено')
                return HttpResponse('Forbidden', status=403)

        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not token:
            return HttpResponse('Bot not configured', status=503)

        try:
            data = json.loads(request.body)
        except Exception:
            return HttpResponse('Bad request', status=400)

        asyncio.run(self._process_update(token, data))
        return HttpResponse('ok')

    @staticmethod
    async def _process_update(token: str, data: dict) -> None:
        from aiogram import Bot, Dispatcher
        from aiogram.types import Update

        from telegram_bot.handlers import router
        from telegram_bot.middleware import UserBindingMiddleware

        bot = Bot(token=token)
        dp = Dispatcher()
        dp.include_router(router)
        dp.message.middleware(UserBindingMiddleware())
        try:
            update = Update.model_validate(data)
            await dp.feed_update(bot, update)
        finally:
            await bot.session.close()
