from functools import lru_cache

from aiogram import Dispatcher

from telegram_bot.handlers import router
from telegram_bot.middleware import UserBindingMiddleware


@lru_cache(maxsize=1)
def get_dispatcher() -> Dispatcher:
    """
    Один диспетчер на процесс — для polling и для webhook.

    Роутер из handlers.py — модульный объект, а aiogram позволяет подключить
    роутер только к одному родителю. Раньше webhook-вью собирало новый
    Dispatcher на каждый запрос: первый апдейт проходил, каждый следующий
    падал с RuntimeError 'Router is already attached' и отдавал 500.
    """
    dp = Dispatcher()
    dp.include_router(router)
    dp.message.middleware(UserBindingMiddleware())
    return dp
