from typing import Any, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class UserBindingMiddleware(BaseMiddleware):
    """
    Ищет привязанного Django-пользователя по telegram_id и кладёт его в data.
    Доступен в хендлерах как `telegram_user` и `is_linked`.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Any],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from asgiref.sync import sync_to_async
        from django.contrib.auth import get_user_model

        data['telegram_user'] = None
        data['is_linked'] = False

        from_user = getattr(event, 'from_user', None)
        telegram_id = from_user.id if from_user else None

        if telegram_id:
            User = get_user_model()
            user = await sync_to_async(
                lambda: User.objects.filter(telegram_id=telegram_id).first()
            )()
            if user:
                data['telegram_user'] = user
                data['is_linked'] = True

        return await handler(event, data)
