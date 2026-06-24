import logging
import uuid

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)
router = Router(name='autoforyou')


# ─── /start ──────────────────────────────────────────────────────────────────

@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message: Message, command: CommandObject) -> None:
    payload = command.args or ''
    if payload.startswith('link_'):
        await _handle_link_token(message, payload[5:])
    else:
        await message.answer(
            'Ласкаво просимо до AUTOforYOU!\n'
            'Для прив\'язки акаунту скористайтесь кнопкою в особистому кабінеті.'
        )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        'Ласкаво просимо до AUTOforYOU! 🚗\n\n'
        '/help — список команд\n'
        '/latest — останні оголошення\n\n'
        'Щоб отримувати сповіщення — прив\'яжіть акаунт у особистому кабінеті.'
    )


# ─── /help ───────────────────────────────────────────────────────────────────

@router.message(Command('help'))
async def cmd_help(message: Message) -> None:
    await message.answer(
        '<b>Команди бота:</b>\n'
        '/start — привітання\n'
        '/help — ця довідка\n'
        '/latest — 3–5 свіжих оголошень (в наявності або в дорозі)',
        parse_mode='HTML',
    )


# ─── /latest ─────────────────────────────────────────────────────────────────

@router.message(Command('latest'))
async def cmd_latest(message: Message) -> None:
    from asgiref.sync import sync_to_async
    from django.conf import settings

    @sync_to_async
    def _fetch():
        from listings.models import Listing
        qs = (
            Listing.objects
            .filter(status__in=['in_stock', 'in_transit'], channel='retail')
            .select_related('vehicle')
            .prefetch_related('vehicle__images')
            .order_by('-created_at')[:5]
        )
        result = []
        for listing in qs:
            v = listing.vehicle
            img = (
                v.images.filter(is_primary=True).first()
                or v.images.first()
            )
            result.append({
                'id': listing.pk,
                'title': f'{v.make} {v.model} {v.year}',
                'price': f'{listing.price} {listing.currency}',
                'status': listing.get_status_display(),
                'photo_url': (img.source_url or '') if img else '',
            })
        return result

    items = await _fetch()
    if not items:
        await message.answer('Наразі немає активних оголошень.')
        return

    site_url = getattr(settings, 'SITE_URL', 'https://autoforyou.ua')
    for item in items:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text='Переглянути',
                url=f'{site_url}/listings/{item["id"]}',
            )
        ]])
        text = (
            f'🚗 <b>{item["title"]}</b>\n'
            f'💵 {item["price"]}\n'
            f'📦 {item["status"]}'
        )
        await message.answer(text, reply_markup=kb, parse_mode='HTML')


# ─── Deep-link: привязка аккаунта ────────────────────────────────────────────

async def _handle_link_token(message: Message, token_str: str) -> None:
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _process(telegram_id: int, token_str: str) -> str:
        from telegram_bot.models import TelegramLinkToken

        try:
            token_uuid = uuid.UUID(token_str)
            token_obj = TelegramLinkToken.objects.select_related('user').get(token=token_uuid)
        except (ValueError, TelegramLinkToken.DoesNotExist):
            return 'invalid'

        if not token_obj.is_valid():
            return 'expired'

        user = token_obj.user
        user.telegram_id = telegram_id
        user.save(update_fields=['telegram_id'])
        token_obj.used = True
        token_obj.save(update_fields=['used'])
        return 'ok'

    result = await _process(message.from_user.id, token_str)
    if result == 'ok':
        await message.answer('✅ Акаунт успішно прив\'язано до Telegram! Тепер ви отримуватимете сповіщення.')
    elif result == 'expired':
        await message.answer('❌ Посилання застаріло або вже використане. Запросіть нове в особистому кабінеті.')
    else:
        await message.answer('❌ Невалідне посилання. Спробуйте ще раз.')
