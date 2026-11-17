"""Меню команд бота (`set_my_commands`, задача 5.4). Описания - из `BotText` (ключи `cmd_*`)."""
import logging

from telegram_bot.texts import aget_text

logger = logging.getLogger(__name__)

# Порядок = порядок в меню Telegram. Ключ описания - `cmd_<команда>`.
BOT_COMMANDS = ('start', 'help', 'latest', 'unlink')


async def install_bot_commands(bot) -> None:
    """Ставит меню команд. Исключение пробрасывается: вызывающий решает, критично ли это."""
    from aiogram.types import BotCommand

    commands = [BotCommand(command=name, description=await aget_text(f'cmd_{name}')) for name in BOT_COMMANDS]
    await bot.set_my_commands(commands)
